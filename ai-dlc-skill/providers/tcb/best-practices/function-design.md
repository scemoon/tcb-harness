# CloudBase Function Design Best Practices

## Core Principles

1. **Stateless** - Functions should not rely on in-memory state
2. **Idempotent** - Handle duplicate invocations gracefully
3. **Single responsibility** - One function, one purpose
4. **Fail fast** - Validate inputs early, fail with clear errors
5. **Observable** - Log all significant events

## Function Structure

### Recommended Template

```javascript
const tcb = require('@cloudbase/node-sdk');

/**
 * Process user registration
 * @param {Object} event - { userId, email, nickname }
 * @param {Object} context - TCB context info
 */
exports.main = async (event, context) => {
  const startTime = Date.now();

  try {
    // 1. Validate input
    validateInput(event);

    // 2. Initialize TCB
    const app = tcb.init({
      env: process.env.TCB_ENV_ID
    });
    const db = app.database();

    // 3. Business logic
    const result = await processRegistration(db, event);

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
Cold start adds 100-500ms latency when function is idle.

### Solutions

#### 1. Minimize Package Size

```bash
# Bad: Include everything
npm install express mongoose axios lodash

# Good: Only what's needed
npm install @cloudbase/node-sdk
```

Use tree-shaking and ES modules:

```javascript
// Bad: Import entire library
import _ from 'lodash';
const sum = _.sum([1, 2, 3]);

// Good: Import specific function
import sum from 'lodash/sum';
```

#### 2. Keep Dependencies Minimal

```json
{
  "dependencies": {
    "@cloudbase/node-sdk": "^1.0.0"
  }
}
```

Avoid:
- Heavy frameworks (Express not needed for simple functions)
- Large utility libraries (use native methods)
- Redundant dependencies

#### 3. Use Timer Keep-Warm (if needed)

```json
{
  "functions": {
    "my-function": {
      "triggers": [
        {
          "name": "keep-warm",
          "type": "timer",
          "config": "*/5 * * * *"
        }
      ]
    }
  }
}
```

**Note:** This costs invocations. Usually not needed as TCB auto-scales.

#### 4. Allocate More Memory

More memory = faster CPU = faster cold start.

```json
{
  "functions": {
    "my-function": {
      "memory": 512
    }
  }
}
```

## Error Handling Patterns

### Pattern 1: Structured Error Response

```javascript
exports.main = async (event, context) => {
  try {
    // Business logic
    const result = await doSomething(event);
    return { success: true, data: result };

  } catch (error) {
    console.error('Error:', error);

    // Determine error type
    if (error.code === 'DATABASE_PERMISSION_DENIED') {
      return {
        success: false,
        error: 'Database access denied',
        code: 'DB_PERMISSION_ERROR'
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

### Pattern 3: Retry with Backoff (for transient errors)

```javascript
async function withRetry(fn, maxRetries = 3) {
  let lastError;

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // Only retry on transient errors
      if (!isTransientError(error)) {
        throw error;
      }

      // Exponential backoff
      await sleep(Math.pow(2, i) * 100);
    }
  }

  throw lastError;
}

function isTransientError(error) {
  const transientCodes = [
    'ECONNRESET',
    'ETIMEDOUT',
    'REQUEST_LIMIT'
  ];
  return transientCodes.includes(error.code);
}
```

## Timeout Strategy

### Set Appropriate Timeout

```json
{
  "functions": {
    "quick-op": {
      "timeout": 5
    },
    "db-query": {
      "timeout": 30
    },
    "complex-process": {
      "timeout": 60
    }
  }
}
```

### Handle Timeout Gracefully

```javascript
exports.main = async (event, context) => {
  // Create abort controller for timeout
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
      // Return partial result or continuation token
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
exports.main = async (event, context) => {
  const initialMemory = process.memoryUsage();

  // Business logic
  const result = await processLargeDataset(event);

  const finalMemory = process.memoryUsage();
  console.log('Memory:', {
    heapUsed: finalMemory.heapUsed - initialMemory.heapUsed,
    heapTotal: finalMemory.heapTotal,
    rss: finalMemory.rss
  });

  return result;
};
```

### Memory-Efficient Patterns

```javascript
// Bad: Load all data into memory
const allUsers = await db.collection('users').get();

// Good: Process in batches
const MAX_BATCH = 100;
let skip = 0;

while (true) {
  const batch = await db.collection('users')
    .skip(skip)
    .limit(MAX_BATCH)
    .get();

  if (batch.data.length === 0) break;

  await processBatch(batch.data);
  skip += MAX_BATCH;
}
```

## Async Patterns

### Await Parallel Operations

```javascript
exports.main = async (event, context) => {
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
exports.main = async (event, context) => {
  const items = event.items || [];

  // Process in parallel with concurrency limit
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
exports.main = async (event, context) => {
  console.log(JSON.stringify({
    level: 'info',
    message: 'Processing request',
    requestId: context.request_id,
    userId: event.userId,
    action: event.action,
    timestamp: new Date().toISOString()
  }));

  try {
    const result = await processEvent(event);

    console.log(JSON.stringify({
      level: 'info',
      message: 'Request completed',
      requestId: context.request_id,
      duration: Date.now() - startTime,
      resultSize: JSON.stringify(result).length
    }));

    return result;

  } catch (error) {
    console.log(JSON.stringify({
      level: 'error',
      message: 'Request failed',
      requestId: context.request_id,
      error: error.message,
      stack: error.stack
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

  // Remove potentially dangerous characters
  return input.replace(/[<>'"]/g, '');
}

function validateObject(obj, schema) {
  for (const [key, type] of Object.entries(schema)) {
    if (typeof obj[key] !== type) {
      throw new Error(`Invalid type for ${key}: expected ${type}`);
    }
  }
}
```

### Don't Log Sensitive Data

```javascript
// Bad
console.log('User login:', { password: event.password });

// Good
console.log('User login:', { userId: event.userId });
```

## Testing Functions Locally

```javascript
// test/functions/my-function.test.js
const handler = require('../functions/my-function/index');

describe('my-function', () => {
  it('should process valid event', async () => {
    const event = {
      userId: 'user-123',
      email: 'test@example.com'
    };

    const result = await handler.main(event, {});

    expect(result.success).toBe(true);
    expect(result.data).toBeDefined();
  });

  it('should reject invalid email', async () => {
    const event = {
      userId: 'user-123',
      email: 'invalid-email'
    };

    const result = await handler.main(event, {});

    expect(result.success).toBe(false);
    expect(result.code).toBe('VALIDATION_ERROR');
  });
});
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
- [ ] Use connection pooling for database

## Troubleshooting

For common issues → `../best-practices/troubleshooting.md`
