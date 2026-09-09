#!/usr/bin/env python3
"""cls_search.py — CLS (Cloud Log Service) log searcher for TCB/SCF.

Search SCF function logs via Tencent Cloud CLS (Cloud Log Service).
Supports requestId tracing, keyword search, and time-range queries.

Usage:
    cdh cls search --request-id <id> --function <name> [--env <env-id>]
    cdh cls search --function <name> --keyword <kw> [--limit N]
    cdh cls search --function <name> --start-time <datetime> --end-time <datetime>

Requirements:
    pip install tencentcloud-sdk-python

Note:
    SCF logs are automatically shipped to CLS since 2021-01-29.
    The SCF logset is named "SCF_logset" and topics follow
    "SCF_logtopic_{functionName}_{namespace}" pattern.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from tencentcloud.common import credential
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
        TencentCloudSDKException,
    )
    from tencentcloud.cls.v20191010 import cls_client
    from tencentcloud.cls.v20191010 import models as cls_models

    _HAS_TENCENTCLOUD_SDK = True
except ImportError:
    _HAS_TENCENTCLOUD_SDK = False


_JSON_MODE: bool = False


def _log(level: str, msg: str, **extra: Any) -> None:
    payload: Dict[str, Any] = {
        "level": level,
        "msg": msg,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    payload.update(extra)
    if _JSON_MODE:
        print(json.dumps(payload), file=sys.stderr)
    else:
        line = f"[{level}] {msg}"
        if extra:
            line += " " + json.dumps(extra)
        print(line, file=sys.stderr)


def _get_credential() -> Any:
    secret_id = os.environ.get("TENCENTCLOUD_SECRETID") or os.environ.get(
        "TCB_SECRET_ID"
    )
    secret_key = os.environ.get("TENCENTCLOUD_SECRETKEY") or os.environ.get(
        "TCB_SECRET_KEY"
    )
    if not secret_id or not secret_key:
        raise ValueError(
            "Missing credentials: set TENCENTCLOUD_SECRETID/SECRETKEY "
            "or TCB_SECRET_ID/SECRET_KEY env vars"
        )
    return credential.Credential(secret_id, secret_key)


def _get_topic_id(function_name: str, namespace: str, region: str) -> Optional[str]:
    topic_name = f"SCF_logtopic_{function_name}_{namespace}"
    _log("INFO", f"Looking for log topic: {topic_name}")
    return None


def _build_query(
    request_id: Optional[str] = None,
    function_name: Optional[str] = None,
    keyword: Optional[str] = None,
    namespace: str = "default",
) -> str:
    conditions: List[str] = []

    if request_id:
        conditions.append(f'SCF_RequestId:"{request_id}"')

    if function_name:
        conditions.append(f'SCF_FunctionName:"{function_name}"')

    if namespace:
        conditions.append(f'SCF_Namespace:"{namespace}"')

    if keyword:
        conditions.append(f'SCF_Message:"{keyword}"')

    if not conditions:
        return "*"

    return " AND ".join(conditions)


def _parse_time(time_str: str) -> int:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(time_str, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    try:
        return int(time_str)
    except ValueError:
        raise ValueError(f"Cannot parse time: {time_str}")


class CLSLogSearcher:
    def __init__(self, region: str = "ap-shanghai"):
        if not _HAS_TENCENTCLOUD_SDK:
            raise ImportError(
                "tencentcloud-sdk-python is required. Install with: "
                "pip install tencentcloud-sdk-python"
            )
        self.region = region
        self.cred = _get_credential()
        self.client = cls_client.ClsClient(self.cred, region)

    def _get_logset_id(self) -> Optional[str]:
        req = cls_models.DescribeLogsetsRequest()
        try:
            resp = self.client.DescribeLogsets(req)
            for logset in resp.Logsets or []:
                if logset.LogsetName == "SCF_logset":
                    return logset.LogsetId
            return None
        except TencentCloudSDKException as e:
            _log("ERROR", f"Failed to get logset: {e}")
            return None

    def _get_topic_id_by_name(self, topic_name: str, logset_id: str) -> Optional[str]:
        req = cls_models.DescribeTopicsRequest()
        req.LogsetId = logset_id
        try:
            resp = self.client.DescribeTopics(req)
            for topic in resp.Topics or []:
                if topic.TopicName == topic_name:
                    return topic.TopicId
            return None
        except TencentCloudSDKException as e:
            _log("ERROR", f"Failed to get topic: {e}")
            return None

    def _resolve_topic_id(
        self,
        function_name: Optional[str] = None,
        namespace: str = "default",
        topic_id: Optional[str] = None,
    ) -> str:
        if topic_id:
            return topic_id

        logset_id = self._get_logset_id()
        if not logset_id:
            raise ValueError("SCF_logset not found. Ensure SCF logging is enabled.")

        if function_name:
            topic_name = f"SCF_logtopic_{function_name}_{namespace}"
            resolved = self._get_topic_id_by_name(topic_name, logset_id)
            if resolved:
                return resolved
            _log("WARN", f"Topic {topic_name} not found, searching all SCF topics")

        raise ValueError(
            f"Cannot determine topic_id. Provide --topic-id or use --function to search."
        )

    def search_by_request_id(
        self,
        request_id: str,
        function_name: Optional[str] = None,
        namespace: str = "default",
        topic_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = _build_query(request_id=request_id, function_name=function_name, namespace=namespace)

        end_ts = int(time.time() * 1000) if not end_time else _parse_time(end_time)
        start_ts = end_ts - 3600 * 1000 if not start_time else _parse_time(start_time)

        resolved_topic_id = self._resolve_topic_id(function_name, namespace, topic_id)

        req = cls_models.SearchLogRequest()
        req.TopicId = resolved_topic_id
        req.Query = query
        req.StartTime = start_ts
        req.EndTime = end_ts
        req.Limit = limit

        _log("INFO", f"Searching logs: {query}", topic=resolved_topic_id)

        try:
            resp = self.client.SearchLog(req)
            results: List[Dict[str, Any]] = []

            for coll in resp.Results or []:
                for log in coll.Logs or []:
                    log_entry: Dict[str, Any] = {
                        "time": coll.Time,
                        "request_id": request_id,
                    }
                    for item in log.Content or []:
                        key = item.Key
                        value = item.Value
                        if key == "SCF_Message":
                            log_entry["message"] = value
                        elif key == "SCF_FunctionName":
                            log_entry["function"] = value
                        elif key == "SCF_Namespace":
                            log_entry["namespace"] = value
                        elif key == "SCF_Duration":
                            log_entry["duration_ms"] = int(value)
                        elif key == "SCF_StatusCode":
                            log_entry["status_code"] = int(value)
                        elif key == "SCF_MemUsage":
                            log_entry["memory_bytes"] = int(value)
                        elif key == "SCF_Level":
                            log_entry["level"] = value
                        elif key == "SCF_RetryNum":
                            log_entry["retry_count"] = int(value)
                        else:
                            log_entry[key.lower().replace("scf_", "")] = value
                    results.append(log_entry)

            _log("INFO", f"Found {len(results)} log entries")
            return results

        except TencentCloudSDKException as e:
            _log("ERROR", f"CLS search failed: {e}")
            raise

    def search_scf_logs(
        self,
        query: str,
        function_name: Optional[str] = None,
        namespace: str = "default",
        topic_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if function_name:
            full_query = _build_query(function_name=function_name, namespace=namespace, keyword=query)
        else:
            full_query = query

        end_ts = int(time.time() * 1000) if not end_time else _parse_time(end_time)
        start_ts = end_ts - 3600 * 1000 if not start_time else _parse_time(start_time)

        resolved_topic_id = self._resolve_topic_id(function_name, namespace, topic_id)

        req = cls_models.SearchLogRequest()
        req.TopicId = resolved_topic_id
        req.Query = full_query
        req.StartTime = start_ts
        req.EndTime = end_ts
        req.Limit = limit

        _log("INFO", f"Searching logs: {full_query}", topic=resolved_topic_id)

        try:
            resp = self.client.SearchLog(req)
            results: List[Dict[str, Any]] = []

            for coll in resp.Results or []:
                for log in coll.Logs or []:
                    log_entry: Dict[str, Any] = {
                        "time": coll.Time,
                    }
                    for item in log.Content or []:
                        key = item.Key
                        value = item.Value
                        if key == "SCF_Message":
                            log_entry["message"] = value
                        elif key == "SCF_FunctionName":
                            log_entry["function"] = value
                        elif key == "SCF_RequestId":
                            log_entry["request_id"] = value
                        elif key == "SCF_Duration":
                            log_entry["duration_ms"] = int(value)
                        elif key == "SCF_StatusCode":
                            log_entry["status_code"] = int(value)
                        elif key == "SCF_Level":
                            log_entry["level"] = value
                        else:
                            log_entry[key.lower().replace("scf_", "")] = value
                    results.append(log_entry)

            _log("INFO", f"Found {len(results)} log entries")
            return results

        except TencentCloudSDKException as e:
            _log("ERROR", f"CLS search failed: {e}")
            raise


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Search SCF logs via Tencent Cloud CLS"
    )
    parser.add_argument("--request-id", help="SCF RequestId to search for")
    parser.add_argument("--function", help="Function name to search")
    parser.add_argument("--namespace", default="default", help="SCF namespace (default: default)")
    parser.add_argument("--keyword", help="Keyword to search in SCF_Message")
    parser.add_argument("--topic-id", help="CLS topic ID (auto-detected if not provided)")
    parser.add_argument("--region", default="ap-shanghai", help="Tencent Cloud region")
    parser.add_argument("--env", help="TCB environment ID (sets region context)")
    parser.add_argument("--start-time", help="Start time (ISO format or Unix ms)")
    parser.add_argument("--end-time", help="End time (ISO format or Unix ms)")
    parser.add_argument("--limit", type=int, default=100, help="Max results (default: 100)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    global _JSON_MODE
    _JSON_MODE = args.json

    if not args.request_id and not args.keyword and not args.function:
        parser.error("At least one of --request-id, --keyword, or --function is required")

    if args.env:
        os.environ.setdefault("TCB_ENV_ID", args.env)

    try:
        searcher = CLSLogSearcher(region=args.region)

        if args.request_id:
            results = searcher.search_by_request_id(
                request_id=args.request_id,
                function_name=args.function,
                namespace=args.namespace,
                topic_id=args.topic_id,
                start_time=args.start_time,
                end_time=args.end_time,
                limit=args.limit,
            )
        else:
            results = searcher.search_scf_logs(
                query=args.keyword or "*",
                function_name=args.function,
                namespace=args.namespace,
                topic_id=args.topic_id,
                start_time=args.start_time,
                end_time=args.end_time,
                limit=args.limit,
            )

        if args.output == "json" or args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            for log in results:
                time_str = log.get("time", "")
                msg = log.get("message", "")
                func = log.get("function", "")
                req_id = log.get("request_id", "")
                level = log.get("level", "INFO")
                duration = log.get("duration_ms", 0)
                status = log.get("status_code", 0)

                header = f"[{time_str}]"
                if req_id:
                    header += f" {req_id[:16]}..."
                if func:
                    header += f" {func}"
                header += f" [{level}]"
                if duration:
                    header += f" {duration}ms"
                if status:
                    header += f" {status}"

                print(header)
                if msg:
                    print(f"  {msg}")
                print()

    except TencentCloudSDKException as e:
        _log("ERROR", f"CLS error: {e}")
        sys.exit(1)
    except Exception as e:
        _log("ERROR", f"{e}")
        sys.exit(1)


if __name__ == "__main__":
    _main()
