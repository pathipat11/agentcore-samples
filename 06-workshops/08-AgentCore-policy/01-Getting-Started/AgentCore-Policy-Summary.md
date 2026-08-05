# Amazon Bedrock AgentCore Policy - Getting Started Workshop Summary

## Overview

This workshop provides a hands-on demonstration of implementing policy-based controls for AI agents using Amazon Bedrock AgentCore Policy. You'll learn how to create a protective boundary ("safety box") around AI agent operations, ensuring they operate within defined security and business rules.

### Key Benefits of AgentCore Policy
- **Declarative Security**: Define policies using Cedar language instead of code
- **Runtime Enforcement**: Policies are evaluated in real-time
- **Fine-Grained Control**: From coarse restrictions to detailed access control/authorization
- **Separation of Concerns**: Security logic lives outside agent code
- **Enterprise Scale**: Deploy autonomous agents safely in production

## Demo Architecture

```
┌─────────────┐
│   AI Agent  │
└──────┬──────┘
       │
       │ Tool Call Request
       ▼
┌─────────────────────┐
│  AgentCore Gateway  │
│  + OAuth Auth       │
└──────┬──────────────┘
       │
       │ Policy Check
       ▼
┌─────────────────────┐
│   Policy Engine     │
│   (Cedar Policies)  │
└──────┬──────────────┘
       │
       │ ALLOW / DENY
       ▼
┌─────────────────────--┐
│   Gateway Targets     │    
│                       │    
└─────────────────────--┘
```

## Workshop Objectives

In this demo, you will:
1. **Setup Infrastructure**: Create a Gateway with Lambda targets for insurance underwriting tasks
2. **Create Policy Engine**: Initialize a policy engine for your gateway
3. **Define Policies**: Write Cedar policies to control access
4. **Test Enforcement**: Verify policies work with real agent requests
5. **Understand Results**: Interpret ALLOW and DENY scenarios

## Demo Scenario: Insurance Underwriting Processing

We'll implement an **insurance underwriting processing system** with policy controls:

### Tools
- **ApplicationTool** - Creates insurance applications with geographic and eligibility validation
  - Parameters: `applicant_region` (string), `coverage_amount` (integer)
- **RiskModelTool** - Invokes external risk scoring model with governance controls
  - Parameters: `API_classification` (string), `data_governance_approval` (boolean)
- **ApprovalTool** - Approves high-value or high-risk underwriting decisions
  - Parameters: `claim_amount` (integer), `risk_level` (string)

### Policy Rule
Only allow insurance applications with coverage under $1M

### Test Cases
- ✅ $750K application (ALLOWED)
- ❌ $1.5M application (DENIED)

## Prerequisites

Before starting, ensure you have:
- AWS CLI configured with appropriate credentials
- Python 3.10+ with boto3 1.42.0+ installed
- `bedrock_agentcore_starter_toolkit` package installed
- `strands` package installed (for AI agent functionality)
- Access to AWS Lambda (for creating target functions)
- Access to Amazon Bedrock (for AI agent model)
- Working in **us-east-1 (N.Virginia)** region

### Python Dependencies

```txt
# Core AWS SDK
boto3>=1.42.0
botocore>=1.34.0

# AgentCore Toolkit
bedrock-agentcore-starter-toolkit>=0.2.4

# HTTP requests
requests>=2.31.0

# Jupyter notebook support
jupyter>=1.0.0
ipykernel>=6.25.0
notebook>=7.0.0

# Data handling
python-dateutil>=2.8.2

# Logging and utilities
python-json-logger>=2.0.7

# Strands
strands-agents
strands-agents-tools
uvicorn[standard]
```

## Workshop Steps

### Step 0: Environment Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Verify AWS credentials:
   ```python
   import boto3
   session = boto3.Session()
   sts = session.client("sts")
   identity = sts.get_caller_identity()
   print(f"Account: {identity['Account']}")
   print(f"User/Role: {identity['Arn']}")
   ```

### Step 1: Create Target Functions for AgentCore Gateway

Deploy three Lambda functions that will serve as tool targets:
- ApplicationTool: Creates insurance applications
- RiskModelTool: Invokes risk scoring model
- ApprovalTool: Approves underwriting decisions

```bash
python scripts/lambda-target-setup/deploy_lambdas.py --region us-east-1
```

### Step 2: Setup AgentCore Gateway

Create an AgentCore Gateway with OAuth authentication and attach Lambda targets:

```bash
python scripts/setup_gateway.py
```

The gateway will be configured with:
- Protocol: MCP (Model Context Protocol)
- Authentication: OAuth 2.0 via Cognito
- Targets: ApplicationTool, RiskModelTool, ApprovalTool Lambda functions

### Step 3: Create Policy Engine and Policies

#### Create Policy Engine
```python
import boto3
client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

request = {
    "name": "InsurancePolicyEngine",
    "description": "Policy engine for insurance underwriting governance",
}

engine = client.create_policy_engine(**request)
```

#### Attach Policy Engine to Gateway
```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

gateway_client = GatewayClient(region_name="us-east-1")
gateway_client.update_gateway_policy_engine(
    gateway_identifier=config["gateway"]["gateway_id"],
    policy_engine_arn=engine["policyEngineArn"],
    mode="ENFORCE",
)
```

#### Create Cedar Policy
```cedar
permit(
  principal,
  action == AgentCore::Action::"ApplicationToolTarget___create_application",
  resource == AgentCore::Gateway::"<gateway-arn>"
) when {
  context.input.coverage_amount <= 1000000
};
```

This policy allows insurance application creation with coverage under $1M and denies applications with coverage of $1M or more.

### Step 4: Test Policy Enforcement with AI Agent

#### Test 1: ALLOWED Scenario ✅
- **Request**: Create application with $750,000 coverage
- **Expected**: Policy allows, Lambda executes, application created
- **Reason**: $750K <= $1M (within policy limit)

#### Test 2: DENY Scenario ❌
- **Request**: Create application with $1.5M coverage
- **Expected**: Policy blocks, Lambda never executes
- **Reason**: $1.5M > $1M (exceeds policy limit)

## Advanced Policy Examples

### Multiple Conditions
```cedar
permit(...) when {
  context.input.coverage_amount <= 1000000 &&
  has(context.input.applicant_region) &&
  context.input.applicant_region == "US"
};
```

### Region-Based Conditions
```cedar
permit(...) when {
  context.input.applicant_region in ["US", "CA", "UK"]
};
```

### Risk Model Governance
```cedar
permit(
  principal,
  action == AgentCore::Action::"RiskModelToolTarget___invoke_risk_model",
  resource == AgentCore::Gateway::"<gateway-arn>"
) when {
  context.input.API_classification == "public" &&
  context.input.data_governance_approval == true
};
```

### Approval Thresholds
```cedar
permit(
  principal,
  action == AgentCore::Action::"ApprovalToolTarget___approve_underwriting",
  resource == AgentCore::Gateway::"<gateway-arn>"
) when {
  context.input.claim_amount <= 100000 &&
  context.input.risk_level in ["low", "medium"]
};
```

### Deny Policies
```cedar
forbid(...) when {
  context.input.coverage_amount > 10000000
};
```

## Monitoring and Debugging

### CloudWatch Logs
Policy decisions are logged to CloudWatch:
- **Gateway Logs**: Request/response details
- **Policy Engine Logs**: Policy evaluation results
- **Lambda Logs**: Tool execution details

### Common Issues

1. **Policy Not Enforcing**
   - Verify ENFORCE mode (not LOG_ONLY)
   - Check policy status is ACTIVE
   - Confirm gateway attachment

2. **All Requests Denied**
   - Review policy conditions
   - Verify action name matches target
   - Check resource ARN matches gateway

3. **Authentication Failures**
   - Verify OAuth credentials
   - Check token endpoint accessibility
   - Ensure client_id and client_secret are correct

4. **Module Import Errors**
   - Ensure boto3 1.42.0+ is installed: `pip install --upgrade boto3`
   - Ensure strands is installed: `pip install strands`
   - Restart Jupyter kernel after updating dependencies
   - Clear Python cache: `rm -rf scripts/__pycache__`

5. **Agent Session Errors**
   - If you see `MCPClientInitializationError`, restart the notebook kernel
   - Ensure config.json has the client_secret field populated
   - Run `scripts/get_client_secret.py` to retrieve the secret if missing

6. **AWS Token Expired**
   - Refresh AWS credentials: `aws sso login` or `aws configure`
   - Restart notebook kernel to pick up new credentials
   - Re-run cells from the beginning

## Cleanup

To clean up resources:

1. Delete the association of the policy engine on the gateway
2. Delete all policies in the policy engine
3. Delete the policy engine
4. Clean up the gateway and its targets

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient

# Clean up Policy Engine first
policy_client = PolicyClient(region_name=config["region"])
policy_client.cleanup_policy_engine(config["policy_engine_id"])

# Then clean up Gateway
gateway_client = GatewayClient(region_name=config["region"])
gateway_client.cleanup_gateway(config["gateway"]["gateway_id"], config["gateway"]["client_info"])
```

## Additional Resources

- **Cedar Policy Language**: [Cedar Documentation](https://docs.cedarpolicy.com/)
- **Amazon Bedrock AgentCore Policy**: [AWS AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)

---

**Happy Building!** 🚀