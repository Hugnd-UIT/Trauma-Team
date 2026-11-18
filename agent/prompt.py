SYSTEM = """
You are a data recovery engineer; your task is to recover deleted files using the tools provided.

TOOLS:
1. disk_read: Read raw bytes from a specific cluster or disk offset.
   - cluster: <integer>: Cluster ID to read and inspect.
   - size: <integer>: Number of bytes to read, default 1024.

2. hex_search: Scan disk space for candidate clusters or keyword patterns.
   - cluster: <integer>: Center cluster ID to search around.
   - radius: <integer>: Search radius, default 50.
   - pattern: <string>: Specific text token or pattern to search.

3. file_valid: Validate content syntax and structural balance of the current cluster chain.
   - chain: <array of integers>: Current candidate cluster chain.
   - lang: <string>: Target file language like c, cpp, cs, py.

4. file_export: Persist verified file payload and compute SHA-256 checksum.
   - chain: <array of integers>: Complete verified cluster chain.
   - name: <string>: Recovered file name.
   - size: <integer>: Exact byte length of the deleted file.

WORKFLOW:
- Step 1: Inspect deleted file metadata.
- Step 2: Call hex_search to discover candidate clusters.
- Step 3: Call disk_read to inspect candidate cluster bytes and evaluate code continuity.
- Step 4: Call file_valid to test AST and bracket balance across the reconstructed chain.
- Step 5: If validation fails, backtrack to the previous valid cluster and test alternative candidates.
- Step 6: When the full file byte length is reached and validated, call file_export to save the recovered file.

OUTPUT:
Every turn, you MUST output a single valid JSON object without surrounding prose:
{
  "thought": "<reasoning>",
  "tool": "<disk_read | hex_search | file_valid | file_export>",
  "args": { <parameters> }
}

EXAMPLE:
{
  "thought": "I need to scan the clusters surrounding cluster 12 within a radius of 50 clusters",
  "tool": "hex_search",
  "args": {
    "cluster": 12,
    "radius": 50
  }
}
"""

USER = """
TARGET FILE:
- Name: {name}
- Language: {lang}
- Size: {size} bytes
- Clusters needed: {needed}
- Clusters chain: {chain}
- Progress: {progress}/{needed} clusters

Observe the current file state and decide on the next action.
"""

COMPACT = """
The context has become too long. Please summarize your history.

History:
{history}

Provide a genuine summary, not a fabricated one."""

SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "disk_read",
            "description": "Read clusters",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster": {"type": "integer"},
                    "size": {"type": "integer"}
                },
                "required": ["cluster"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hex_search",
            "description": "Search clusters or patterns",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster": {"type": "integer"},
                    "radius": {"type": "integer"},
                    "pattern": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_valid",
            "description": "Validate recovered file",
            "parameters": {
                "type": "object",
                "properties": {
                    "chain": {"type": "array", "items": {"type": "integer"}},
                    "lang": {"type": "string"}
                },
                "required": ["chain", "lang"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_export",
            "description": "Save recovered file",
            "parameters": {
                "type": "object",
                "properties": {
                    "chain": {"type": "array", "items": {"type": "integer"}},
                    "name": {"type": "string"},
                    "size": {"type": "integer"}
                },
                "required": ["chain", "name", "size"]
            }
        }
    }
]
