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

3. file_read: Inspect content of assembled cluster segments.
   - chain: <array of integers or ranges>: Cluster list like [114, 115] or cluster ranges like [[114, 701]].
   - mode: <string>: Read mode like tail, head, range. Default tail.
   - count: <integer>: Number of clusters to read, default 1.
   - start_cluster: <integer>: Starting cluster when mode is range.
   - end_cluster: <integer>: Ending cluster when mode is range.
   - lang: <string>: Target file language like c, py, pptx.

4. file_valid: Validate content syntax and structural balance of the cluster chain.
   - chain: <array of integers or ranges>: Cluster list like [114, 115] or cluster ranges like [[114, 701]] or [[114, 1322], [1324, 2532]].
   - lang: <string>: Target file language like pptx, py, c.

5. file_export: Persist verified file payload and compute SHA-256 checksum.
   - chain: <array of integers or ranges>: Complete cluster list or cluster ranges like [[114, 1322], [1324, 2532]].
   - name: <string>: Recovered file name.
   - size: <integer>: Exact byte length of the deleted file.

WORKFLOW:
- Step 1: Inspect deleted file metadata.
- Step 2: Call hex_search to discover candidate clusters.
- Step 3: Call disk_read to inspect candidate cluster bytes and evaluate code continuity.
- Step 4: Call file_read to inspect the current file.
- Step 5: Call file_valid to test AST and bracket balance across the reconstructed chain.
- Step 6: If validation fails, backtrack to the previous valid cluster and test alternative candidates.
- Step 7: When the full file byte length is reached and validated, call file_export to save the recovered file.

OUTPUT:
Every turn, you MUST output a single valid JSON object without surrounding prose:
{
  "thought": "<reasoning>",
  "tool": "<disk_read | hex_search | file_read | file_valid | file_export>",
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
- Needed: {needed} clusters
- Current chain: {chain}
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
            "name": "file_read",
            "description": "Read assembled cluster segments",
            "parameters": {
                "type": "object",
                "properties": {
                    "chain": {
                        "type": "array",
                        "description": "Cluster list or ranges like [[114, 701]]"
                    },
                    "mode": {
                        "type": "string",
                        "description": "tail, head, or range"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of clusters to read, default 1"
                    },
                    "start_cluster": {"type": "integer"},
                    "end_cluster": {"type": "integer"},
                    "lang": {"type": "string"}
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
                    "chain": {
                        "type": "array",
                        "description": "Cluster list or ranges like [[114, 701]] or [[114, 1322], [1324, 2532]]"
                    },
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
                    "chain": {
                        "type": "array",
                        "description": "Cluster list or ranges like [[114, 1322], [1324, 2532]]"
                    },
                    "name": {"type": "string"},
                    "size": {"type": "integer"}
                },
                "required": ["chain", "name", "size"]
            }
        }
    }
]
