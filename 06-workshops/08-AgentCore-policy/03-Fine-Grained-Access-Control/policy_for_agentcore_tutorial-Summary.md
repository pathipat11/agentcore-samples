# Policy for Amazon Bedrock AgentCore - Fine-Grained Access Control Workshop Summary

## Overview

This workshop demonstrates how to implement **Policy for Amazon Bedrock AgentCore**, enabling fine-grained access control for AI agents in tool invocations using Cedar policies and JWT token claims with enforcement on Amazon Bedrock AgentCore Gateways.

### What You'll Learn

- How to configure Amazon Cognito to add custom claims to JWT tokens
- How to create policies with Cedar that validate JWT claims provided via Amazon Bedrock AgentCore Identity
- How to implement attribute-based access control (ABAC) patterns
- How to test and verify policy enforcement with different claim scenarios with attached Amazon Bedrock AgentCore Gateways

### Key Concepts

**Policy for Amazon Bedrock AgentCore**: A Cedar-based policy engine that evaluates access requests against fine-grained policies, using JWT token claims as principal attributes.

**Amazon Bedrock AgentCore Identity**: Integrates with Amazon Cognito, or any other Identity Provider (IdP) that supports OAuth, to authenticate requests and extract JWT claims for policy evaluation.

**Amazon Bedrock AgentCore Gateway**: An easy and secure way for developers to build, deploy, discover, and connect to tools at scale with MCP.

**[Cedar Policies](https://www.cedarpolicy.com/en)**: Declarative policies that define who (principal) can perform what (action) on which resources, with optional conditions.

## Architecture

The workshop follows this architecture:

```
                                ┌───────────────────────┐
                                │  Policy for AgentCore │ 
                                │  (Cedar Policies)     │ 
                                │                       │ 
                                │  Evaluates:           │ 
                                │  - principal tags     │ 
                                │  - context.input      │ 
                                │  - resource           │ 
                                └───────────┬───────────┘ 
                                            │ attached 
                                            ▼ 
┌─────────────────┐             ┌───────────────────────┐             ┌─────────────┐
│   Amazon        │  JWT Token  │  Amazon Bedrock       │             │   Lambda    │
│   Cognito       │────────────▶│  AgentCore Gateway    │────────────▶│   Target    │
│   + AWS Lambda  │  with       │                       │  if ALLOWED │   (Tool)    │
└─────────────────┘  claims     └───────────────────────┘             └─────────────┘
```

### Key Components

1. **Amazon Cognito**: Generates JWT tokens with custom claims
2. **AWS Lambda**: Pre-token generation trigger adds custom claims to JWT tokens
3. **Amazon Bedrock AgentCore Gateway**: Enforces Cedar policies on tool invocations
4. **Policy Engine**: Stores and evaluates Cedar policies
5. **Lambda Targets**: Business logic implementation (RefundToolTarget in this workshop)

## Workshop Structure

### Part 1: Setup and Configuration

1. **Install Dependencies**: Required Python packages
2. **Load Configuration**: `gateway_config.json` with gateway details and Cognito client information
3. **Initialize AWS Clients**: Boto3 clients for Lambda, Cognito, IAM, STS, and AgentCore Control
4. **Validate Gateway Authorizer**: Ensure Cognito access tokens are properly configured

### Part 2: Helper Functions

Utility functions for:
- Getting bearer tokens using OAuth2 client credentials flow
- Decoding JWT tokens to inspect claims
- Making gateway requests
- Analyzing responses (ALLOWED/DENIED/ERROR)
- Displaying test results

### Part 3: Configure Amazon Cognito Lambda Trigger

**Important Notes**:
- For M2M (machine-to-machine) client credentials flow, use AWS Lambda trigger version **V3_0**
- V3_0 requires Amazon Cognito **Essentials** or **Plus** tier
- Lambda function adds custom claims like `department_name`, `groups`, etc. to JWT tokens
- These claims become **principal tags** in Cedar policies

### Part 4: Policy Engine Functions

Functions to interact with the Policy for Amazon Bedrock AgentCore service:
- Create policy engines
- Get policy engine details
- Wait for policy engines to become ACTIVE
- Create Cedar policies
- Get policy details
- Wait for policies to become ACTIVE
- Delete policies
- List all policies

### Cedar Policy Syntax for JWT Claims

JWT claims are accessed via **principal tags** in Cedar policies:

| Pattern | Cedar Syntax |
|---------|-------------|
| Check claim exists | `principal.hasTag("claim_name")` |
| Exact match | `principal.getTag("claim_name") == "value"` |
| Pattern match | `principal.getTag("claim_name") like "*value*"` |
| Input validation | `context.input.field <= value` |

### Part 5: Test Scenario 1 - Department-Based Access Control

**Cedar Policy Pattern**:
```cedar
permit(principal, action, resource)
when {
    principal.hasTag("department_name") &&
    principal.getTag("department_name") == "finance"
};
```

**Tests**:
- Request with `department_name='finance'` → **ALLOWED**
- Request with `department_name='engineering'` → **DENIED**

### Part 6: Test Scenario 2 - Groups-Based Access Control

**Cedar Policy Pattern** (using `like` operator for pattern matching):
```cedar
permit(principal, action, resource)
when {
    principal.hasTag("groups") &&
    principal.getTag("groups") like "*admins*"
};
```

**Tests**:
- Request with groups containing "admins" → **ALLOWED**
- Request without "admins" group → **DENIED**

### Part 7: Test Scenario 3 - Principal ID-Based Access Control

**Cedar Policy Pattern** (using `sub` claim which equals client_id in Client Credentials Flow):
```cedar
permit(principal, action, resource)
when {
    principal.hasTag("sub") &&
    principal.getTag("sub") == "your-client-id"
};
```

### Part 8: Advanced Patterns

**Combined Conditions**:
```cedar
permit(principal,
    action == AgentCore::Action::"RefundToolTarget___refund",
    resource == AgentCore::Gateway::"<gateway-arn>")
when {
    principal.hasTag("department_name") &&
    principal.getTag("department_name") == "finance" &&
    context.input.amount <= 1000
};
```

**Pattern Matching with `like` Operator**:
- `"*admin*"` - Contains "admin" anywhere
- `"admin*"` - Starts with "admin" 
- `"*admin"` - Ends with "admin"
- `"team-*"` - Starts with "team-"

### Part 9: Best Practices

**Policy Design Best Practices**:
1. Use specific actions rather than wildcards
2. Always check claim existence with `hasTag()` before `getTag()`
3. Use pattern matching carefully - `like "*value*"` can match unintended strings
4. Test both ALLOW and DENY scenarios
5. Document policies with descriptive names and descriptions

**Amazon Cognito Configuration Best Practices**:
1. Use V3_0 trigger for M2M client credentials flow
2. Upgrade to Essentials tier for V3_0 support
3. Test token claims before creating policies
4. Handle arrays carefully - they are serialized as strings in JWT claims

**Common Pitfalls to Avoid**:
- Using V1_0 or V2_0 trigger with M2M flow (claims won't be added)
- Forgetting to check `hasTag()` before `getTag()`
- Using exact match (`==`) when pattern match (`like`) is needed for arrays
- Not waiting for policy to become ACTIVE before testing
- Creating policies without proper cleanup strategy

### Part 10: Required AWS IAM Permissions

**For Policy Management**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "policy-registry:CreatePolicyEngine",
        "policy-registry:GetPolicyEngine",
        "policy-registry:ListPolicyEngines",
        "policy-registry:CreatePolicy",
        "policy-registry:DeletePolicy",
        "policy-registry:ListPolicies"
      ],
      "Resource": "*"
    }
  ]
}
```

**For Amazon Cognito AWS Lambda Trigger**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cognito-idp:UpdateUserPool",
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:AddPermission",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PassRole"
      ],
      "Resource": "*"
    }
  ]
}
```

### Part 11: Cleanup

Delete all policies created during the tutorial:
```python
print("Deleting policies...")
for pid in CREATED_POLICIES:
    delete_policy(pid)
CREATED_POLICIES.clear()
print("✓ Cleanup complete")
```

## Conclusion

Congratulations! You've completed the Policy for Amazon Bedrock AgentCore tutorial. You've learned how to:

✅ Configure Amazon Cognito AWS Lambda triggers to add custom claims to JWT tokens  
✅ Create Cedar policies that validate JWT claims via principal tags  
✅ Implement department-based access control  
✅ Implement groups-based access control with pattern matching  
✅ Implement principal ID-based access control  
✅ Combine multiple conditions for complex access control scenarios  

### Key Cedar Syntax Patterns

| Claim Type | Cedar Syntax |
|------------|-------------|
| String (exact) | `principal.getTag("claim") == "value"` |
| String (contains) | `principal.getTag("claim") like "*value*"` |
| Array (contains) | `principal.getTag("claim") like "*value*"` |
| Input validation | `context.input.field <= value` |

### Next Steps

1. **Implement in production** - Apply these patterns to your Amazon Bedrock AgentCore deployments
2. **Customize policies** - Tailor policies to your specific access control requirements
3. **Add monitoring** - Set up Amazon CloudWatch alarms for policy denials
4. **Iterate and improve** - Refine policies based on real-world usage

---
**Author**: AWS  
**License**: MIT-0  
**Last Updated**: 2025