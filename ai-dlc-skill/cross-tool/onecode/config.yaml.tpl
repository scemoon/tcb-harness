# .cdh/config.yaml — AI-DLC 项目配置
name: {{project_name}}
platform: {{cloud_provider}}  # tcb | aliyun
phase: {{current_phase}}     # understand | plan | verify | deliver

# compute_mode: fc | sae | cloudbase-functions | cloudbase-run
compute_mode: {{compute_mode}}

stack:
  components:
    - native
    - desktop
    - web
    - backend
    - wxa
    - mya
    - tta
