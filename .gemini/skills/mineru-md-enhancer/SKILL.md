---
name: mineru-md-enhancer
description: Instructs the code agent to generate and execute a Python script that restores nested subject header hierarchies in MinerU-generated Markdown files. Enforces token efficiency by only sending extracted headers to the LLM.
---

# MinerU Markdown Enhancer Skill

When the user asks to enhance, fix, or restore the headers of a MinerU Markdown file, you MUST follow these steps in order:

1.  **Read Template:** Read the provided `.gemini/skills/mineru-md-enhancer/references/template.py` file.
2.  **Generate Code:** Act as an expert Python engineer. Write a complete Python script named `restore_md.py`  with reference to `template.py`. You MUST implement the missing logic (`# TODO` sections) to:
    * Read the target Markdown file.
    * Extract ONLY the header lines (lines starting with `#`). **CRITICAL: Do not send the full document body to the LLM.**
    * Send a list of the extracted headers to the LLM API. Instruct the LLM to determine the correct hierarchy based on prefix hints (e.g., `1.1`, `A.`) and return the corrected headers.
    * Parse the LLM response and map the corrected headers back to the original document's structure.
    * Overwrite the target Markdown file with the corrected content.
3.  **Environment Check:** Verify a `.env` file exists in the working directory with `LLM_HOST_PATH`, `LLM_MODEL_NAME`, and `LLM_API_KEY`.
4.  **Execute:** use pydantic to enforce  type-safe, and structured interaction with llm.
5.  **Report:** Confirm successful execution and summarize the hierarchy changes made to prepare the document for downstream parsing.