# Amazon Bedrock AgentCore Policy - NL2Cedar Workshop Summary

## Overview

This workshop guides you through the complete workflow of generating Cedar policies from natural language using Amazon Bedrock AgentCore Policy's NL2Cedar (Natural Language to Cedar) capability. You'll learn how to:

- Create a Policy Engine to hold Cedar policies
- Generate Cedar policies from natural language statements
- Work with different types of policy generations (single-line, multi-line, principal-related statements)
- Validate and create policies in your Policy Engine
- Clean up resources after the workshop

## Architecture

The NL2Cedar workflow follows this architecture:

```
┌─────────────────────┐
│ Natural Language    │
│ Input (NL2Cedar)    │
└──────┬──────────────┘
        │
        │ Generation Request
        ▼
┌─────────────────────┐
│   NL2Cedar Service  │
│ (Bedrock AgentCore) │
└──────┬──────────────┘
        │
        │ Generated Cedar Policy
        ▼
┌─────────────────────┐
│    Policy Engine    │
│   (Cedar Policies)  │
└──────┬──────────────┘
        │
        │ Policy Check
        ▼
┌─────────────────────┐
│   AgentCore Gateway │
│  + OAuth Auth       │
└──────┬──────────────┘
        │
        │ ALLOW / DENY
        ▼
┌─────────────────────--┐
│   Gateway Targets     │    
│                       │    
└─────────────────────--┘
        │
        │ Lambda Functions
        ▼
┌─────────────────────┐
│ Application Tool    │
│ Risk Model Tool     │
│ Approval Tool       │
└─────────────────────┘
```

### Key Components

1. **Natural Language Input**: Users write policy requirements in natural language
2. **NL2Cedar Service**: Converts natural language to Cedar policy syntax and validates it
3. **Policy Engine**: Stores and manages Cedar policies for enforcement
4. **AgentCore Gateway**: Enforces policies on tool calls from AI agents
5. **Gateway Targets**: Lambda functions that implement the actual business logic

## Prerequisites

Before starting, ensure you have:

- ✅ AWS CLI configured with appropriate credentials
- ✅ Python 3.10+ with boto3 installed
- ✅ `bedrock_agentcore_starter_toolkit` package installed
- ✅ Access to AWS Lambda (for target functions)

This workshop uses the same gateway setup as described in `01-Getting-Started/AgentCore-Policy-Demo.ipynb`, which sets up a Gateway for Insurance Underwriting Use case with 3 Lambda targets.

## Workshop Structure

### Step 0: Environment Setup

1. **Verify AWS Credentials**: The notebook checks your AWS credentials and region configuration
2. **Check Gateway Configuration**: Verifies if the Insurance Underwriting gateway setup from the Getting Started notebook exists
3. **Setup Infrastructure (if needed)**: If the gateway isn't found, the notebook automatically sets up:
   - Lambda functions for Application Tool, Risk Model Tool, and Approval Tool
   - AgentCore Gateway for Insurance Underwriting

### Step 1: Create a Policy Engine

A Policy Engine is a collection of policies that can be associated with a gateway for real-time enforcement of policies on inbound traffic.

**Key Actions:**
- Create a Policy Engine named "InsurancePolicyEngine_NL2Cedar"
- Save Policy Engine information to the configuration file

### Step 2: Generate Policy from Natural Language

The NL2Cedar capability allows you to write authorization requirements in natural language which are automatically converted to Cedar syntax.

#### Gateway Targets

The Insurance Underwriting gateway has 3 Lambda targets:

1. **Application Tool**: Simplified Application Creation
   - Parameters: `applicant_region` (Customer's geographic region), `coverage_amount` (Requested insurance coverage amount)

2. **Risk Model Tool**: Simplified Risk Model Access
   - Parameters: `API_classification` (API classification), `data_governance_approval` (Whether data governance has approved model usage)

3. **Approval Tool**: Insurance Approval Process
   - Parameters: `claim_amount` (Insurance claim/coverage amount), `risk_level` (Risk level assessment)

#### Example: Simple Natural Language Statement

**Natural Language:** "Allow all users to invoke the application tool when the coverage amount is under 1000000 and the applicant region is US or CA"

**Generated Cedar Policy:**
```cedar
permit {
    principal is unknown,
    action is Action::"lambda:InvokeFunction",
    resource is Resource::"lambda:function:ApplicationTool",
    when {
        request.context.coverage_amount < 1000000 &&
        request.context.applicant_region in {"US", "CA"}
    }
}
```

### Policy Validation Findings

When NL2Cedar generates a Cedar policy, it runs the generated Cedar through a multi-step validation process. Findings can be:

| Finding Type | Meaning |
|---|---|
| `INVALID` | Cedar syntax or schema error — may block policy creation under strict mode |
| `WARNING` | Non-blocking issue — policy is syntactically valid but may behave unexpectedly |

To override validation and create policies regardless of findings, use `validation_mode="IGNORE_ALL_FINDINGS"` as a fallback.

### Other Types of Policy Generations from Natural Language

#### 1. Multi-line Statements

When multi-line statements are provided, multiple policies will be generated. The notebook demonstrates:

**Natural Language:**
```
Allow all users to invoke the risk model tool when data governance approval is true. 
Block users from calling the application tool unless coverage amount is present
```

This generates two separate Cedar policies.

#### 2. Principal Related Policy Statements

Policies can assert conditions based on the principal scope (relayed through OAuth access token). Examples include:

- **Username-based access**: "Allow principals with username "test-user" to invoke the risk model tool"
- **Scope-based access**: "Forbid principals to access the approval tool unless they have the scope group:Controller"
- **Role-based access**: "Block principals from using risk model tool and approval tool unless the principal has role "senior-adjuster""

### Step 3: Create Policies from Generated Cedar

After generating Cedar policies, you can create them in your Policy Engine. The notebook shows both successful creation and fallback mechanisms when validation fails.

## Cleanup

After completing the workshop, it's important to clean up resources to avoid unnecessary charges:

1. **Clean up Policy Engine**: Removes the "InsurancePolicyEngine_NL2Cedar" policy engine
2. **Clean up Gateway**: Removes the Insurance Underwriting gateway and associated resources

## Key Learning Outcomes

- Understanding how NL2Cedar converts natural language to Cedar policies
- Learning to work with different types of policy statements (single-line, multi-line, principal-related)
- Understanding policy validation findings and how to handle them
- Practicing the complete workflow from natural language to policy enforcement
- Gaining experience with Amazon Bedrock AgentCore Policy capabilities

## Next Steps

- Explore additional policy patterns and complex conditions
- Integrate NL2Cedar into your existing applications
- Combine NL2Cedar with other AgentCore capabilities for comprehensive governance