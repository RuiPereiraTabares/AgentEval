# API Analysis Prompt

## Instructions

Analyze all code in this repository and identify every API endpoint, SDK call, service integration, and external dependency. Categorize each API by its type and create separate markdown documentation files for each category.

## Task

1. **Scan the entire codebase** for:
   - All API calls, SDK methods, HTTP requests, and service integrations
   - Look at imports, using statements, HTTP clients, and SDK instantiations
   - Check configuration files for API endpoints and base URLs
   - Examine dependency injection registrations for API clients

2. **For each API found, document**:
   - Endpoint/method name
   - HTTP method (if applicable)
   - File location and line number
   - Parameters/payload structure
   - Authentication requirements
   - Brief description of purpose

3. **Categorize into these specific API types**:

### Required Categories (create separate .md file for each)

| File | Description |
|------|-------------|
| `GRAPH_API.md` | Microsoft Graph API calls (users, groups, mail, calendar, teams, directory, etc.) |
| `EXCHANGE_ADMIN_API.md` | Exchange Admin Center APIs, Exchange Online Management, mailbox operations, transport rules |
| `CONFIG_API.md` | Configuration service APIs, settings endpoints, feature flags |
| `CSA_API.md` | CSA (Customer Service & Support) related APIs |
| `MIDDLE_TIER_API.md` | Internal service-to-service API calls within Microsoft infrastructure |
| `THIRD_PARTY_API.md` | Any external non-Microsoft service integrations |

### Dynamic Categories

If you find a **group of 3 or more related APIs** that don't fit the categories above, create a new markdown file with an appropriate descriptive name. Examples:
- If you find multiple Azure DevOps APIs → create `AZURE_DEVOPS_API.md`
- If you find multiple authentication/identity APIs → create `IDENTITY_API.md`
- If you find multiple logging/telemetry APIs → create `TELEMETRY_API.md`

Use your judgment to group logically related APIs together.

## Output Format for Each File

```markdown
# [API Type] APIs

## Summary
- **Total APIs found**: X
- **Files containing these APIs**: Y

---

## APIs

### 1. [API Name/Endpoint]
- **Location**: `path/to/file.cs:lineNumber`
- **Method**: GET / POST / PUT / DELETE / PATCH
- **Endpoint**: `/api/v1/resource` or `client.Method()`
- **Authentication**: Bearer token / Certificate / API Key / Managed Identity
- **Parameters**:
  ```csharp
  // or json/typescript as appropriate
  {
    param1: string,
    param2: int
  }
  ```
- **Description**: What this API does and why it's called

---

### 2. [Next API]
...
```

## Final Deliverable

After creating all individual API files, create an `API_SUMMARY.md` with:

```markdown
# API Summary

## Overview
Total APIs discovered: X

## By Category

| Category | Count | File |
|----------|-------|------|
| Graph API | X | [GRAPH_API.md](./GRAPH_API.md) |
| Exchange Admin API | X | [EXCHANGE_ADMIN_API.md](./EXCHANGE_ADMIN_API.md) |
| Config API | X | [CONFIG_API.md](./CONFIG_API.md) |
| CSA API | X | [CSA_API.md](./CSA_API.md) |
| Middle Tier | X | [MIDDLE_TIER_API.md](./MIDDLE_TIER_API.md) |
| Third Party | X | [THIRD_PARTY_API.md](./THIRD_PARTY_API.md) |
| [Any new categories you created] | X | [FILENAME.md](./FILENAME.md) |

## Notes
- Any observations about API usage patterns
- Potential issues or inconsistencies found
- APIs that might need review
```

## Begin Analysis

Start by exploring the repository structure, then systematically analyze each file. Be thorough—check every file that might contain API calls including tests, utilities, and configuration files.
