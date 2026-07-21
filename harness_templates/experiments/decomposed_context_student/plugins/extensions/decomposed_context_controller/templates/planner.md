Decompose the user's question into at most two independent evidence-retrieval subtasks.

Return exactly one JSON object in this form:
{"subtasks":[{"task":"what this subtask must establish","query":"a concise search query"}]}

Each query must be useful for a corpus search. Do not answer the user question. Do not include markdown or explanation.
