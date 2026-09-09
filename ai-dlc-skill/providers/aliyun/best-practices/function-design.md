# Function Compute Design Best Practices

## Core Principles

1. **Stateless** - Functions should not rely on in-memory state
2. **Idempotent** - Handle duplicate invocations gracefully
3. **Single responsibility** - One function, one purpose
4. **Fail fast** - Validate inputs early, fail with clear errors
5. **Observable** - Log all significant events

## Function Structure

### Recommended Template

```javascript
/**
 * Process user registration
 * @param {Object} event - { userId, email, nickname }
 * @param {Object} context - FC context info
 */
module.exports.handler = async (event, context) => {
  const startTime = Date.now();

  try {
    // 1. Validate input
    validateInput(event);

    // 2. Initialize Aliyun clients
    const OSS = require('ali-oss');
    const client = new OSS({
      region: process.env.ALICLOUD_REGION,
      accessKeyId: process.env.ALIBABA_CLOUD_ACCESS_KEY_ID,
      accessKeySecret: process.env.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
      stsToken: process.env.ALIBABA_CLOUD_SECURITY_TOKEN
    });

    // 3. Business logic
    const result = await processRegistration(client, event);

    // 4. Return success
    return {
      success: true,
      data: result,
      duration: Date.now() - startTime
    };

  } catch (error) {
    // Log error
    console.error('Registration failed:', {
      error: error.message,
      userId: event.userId,
      duration: Date.now() - startTime
    });

    // Return error response
    return {
      success: false,
      error: error.message,
      code: error.code || 'UNKNOWN_ERROR'
    };
  }
};

function validateInput(event) {
  if (!event.email) {
    throw { code: 'INVALID_INPUT', message: 'Email is required' };
  }
  if (!event.email.includes('@')) {
    throw { code: 'INVALID_INPUT', message: 'Invalid email format' };
  }
}
```

## Cold Start Optimization

### Problem
Cold start adds 500ms-2s latency when function is idle.

### Solutions

#### 1. Minimize Package Size

```bash
# Bad: Include everything
npm install express mongoose axios lodash

# Good: Only what's needed
npm install ali-oss
```

#### 2. Keep Dependencies Minimal

Use native methods instead of heavy libraries:

```javascript
// Bad: Large utility library
import _ from 'lodash';
const sum = _.sum([1, 2, 3]);

// Good: Native method
const sum = [1, 2, 3].reduce((a, b) => a + b, 0);
```

#### 3. Provisioned Concurrency (paid)

```yaml
function:
  name: hello
  provisionedConcurrency: 2  # Keep 2 instances warm
```

#### 4. Allocate More Memory

More memory = faster CPU = faster cold start.

```yaml
function:
  name: hello
  memorySize: 512  # More memory = faster CPU
```

## Error Handling Patterns

### Pattern 1: Structured Error Response

```javascript
module.exports.handler = async (event, context) => {
  try {
    // Business logic
    const result = await doSomething(event);
    return { success: true, data: result };

  } catch (error) {
    console.error('Error:', error);

    if (error.code === 'InvalidAccessKeyId') {
      return {
        success: false,
        error: 'Credential error',
        code: 'CREDENTIAL_ERROR'
      };
    }

    return {
      success: false,
      error: 'Internal server error',
      code: 'INTERNAL_ERROR'
    };
  }
};
```

### Pattern 2: Validation Errors

```javascript
function validateEvent(event) {
  const errors = [];

  if (!event.userId) {
    errors.push('userId is required');
  }

  if (!event.email || !event.email.includes('@')) {
    errors.push('Valid email is required');
  }

  if (errors.length > 0) {
    const error = new Error('Validation failed');
    error.code = 'VALIDATION_ERROR';
    error.details = errors;
    throw error;
  }
}
```

### Pattern 3: Retry with Backoff

```javascript
async function withRetry(fn, maxRetries = 3) {
  let lastError;

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (!isTransientError(error)) {
        throw error;
      }

      await sleep(Math.pow(2, i) * 100);
    }
  }

  throw lastError;
}

function isTransientError(error) {
  const transientCodes = ['ETIMEDOUT', 'ECONNRESET', 'Throttling'];
  return transientCodes.includes(error.code);
}
```

## Timeout Strategy

### Set Appropriate Timeout

```yaml
function:
  name: quick-op
  timeout: 5  # Quick operations

  name: db-query
  timeout: 30  # Database operations

  name: complex-process
  timeout: 300  # Long running
```

### Handle Timeout Gracefully

```javascript
module.exports.handler = async (event, context) => {
  const timeout = new Promise((_, reject) => {
    setTimeout(() => reject(new Error('Function timeout')), 55000);
  });

  try {
    const result = await Promise.race([
      longRunningTask(event),
      timeout
    ]);
    return { success: true, data: result };

  } catch (error) {
    if (error.message === 'Function timeout') {
      return {
        success: false,
        error: 'Operation timed out',
        code: 'TIMEOUT',
        partial: true
      };
    }
    throw error;
  }
};
```

## Memory Management

### Monitor Memory Usage

```javascript
module.exports.handler = async (event, context) => {
  const initialMemory = process.memoryUsage();

  const result = await processLargeDataset(event);

  const finalMemory = process.memoryUsage();
  console.log('Memory delta:', {
    heapUsed: (finalMemory.heapUsed - initialMemory.heapUsed) / 1024 / 1024 + 'MB'
  });

  return result;
};
```

### Memory-Efficient Patterns

```javascript
// Bad: Load all data into memory
const allUsers = await getAllUsers();

// Good: Process in batches
async function* batchUsers(batchSize = 100) {
  let marker = '';
  while (true) {
    const batch = await getUsers(marker, batchSize);
    if (batch.items.length === 0) break;
    yield batch.items;
    marker = batch.nextMarker;
  }
}
```

## Async Patterns

### Await Parallel Operations

```javascript
module.exports.handler = async (event, context) => {
  // Bad: Sequential
  const user = await getUser(event.userId);
  const orders = await getOrders(event.userId);
  const preferences = await getPreferences(event.userId);

  // Good: Parallel
  const [user, orders, preferences] = await Promise.all([
    getUser(event.userId),
    getOrders(event.userId),
    getPreferences(event.userId)
  ]);

  return { user, orders, preferences };
};
```

### Handle Array of Items

```javascript
module.exports.handler = async (event, context) => {
  const items = event.items || [];
  const BATCH_SIZE = 10;
  const results = [];

  for (let i = 0; i < items.length; i += BATCH_SIZE) {
    const batch = items.slice(i, i + BATCH_SIZE);
    const batchResults = await Promise.all(
      batch.map(item => processItem(item))
    );
    results.push(...batchResults);
  }

  return { processed: results.length, results };
};
```

## Logging Best Practices

### Structured Logging

```javascript
module.exports.handler = async (event, context) => {
  console.log(JSON.stringify({
    level: 'info',
    message: 'Processing request',
    requestId: context.requestId,
    userId: event.userId,
    timestamp: new Date().toISOString()
  }));

  try {
    const result = await processEvent(event);

    console.log(JSON.stringify({
      level: 'info',
      message: 'Request completed',
      requestId: context.requestId,
      duration: Date.now() - startTime
    }));

    return result;

  } catch (error) {
    console.log(JSON.stringify({
      level: 'error',
      message: 'Request failed',
      requestId: context.requestId,
      error: error.message
    }));
    throw error;
  }
};
```

## Security Best Practices

### Validate All Inputs

```javascript
function sanitizeInput(input) {
  if (typeof input !== 'string') {
    throw new Error('Input must be string');
  }
  return input.replace(/[<>'"]/g, '');
}
```

### Don't Log Sensitive Data

```javascript
// Bad
console.log('User login:', { password: event.password });

// Good
console.log('User login:', { userId: event.userId });
```

## VPC Considerations

### When to Use VPC

- Need to access VPC resources (RDS, ECS)
- Enhanced network isolation required

### VPC Impact on Cold Start

```yaml
service:
  name: my-service
  vpcConfig:
    vpcId: vpc-xxxxx
    vswitchIds: [vsw-xxxxx]
    securityGroupId: sg-xxxxx
  # VPC adds 10-30s to cold start
```

## Performance Checklist

- [ ] Minimize dependencies
- [ ] Use appropriate memory allocation
- [ ] Set realistic timeout
- [ ] Implement error handling
- [ ] Add structured logging
- [ ] Validate inputs
- [ ] Use parallel awaits where possible
- [ ] Process large datasets in batches
- [ ] Avoid keeping state between invocations
- [ ] Use VPC only when needed (cold start impact)

## Troubleshooting

For common issues → `../best-practices/troubleshooting.md`
