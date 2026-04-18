import json
import logging
import os

from memento.prompts.registry import load_prompt
from memento.llm_client import get_llm_client, get_model_name

logger = logging.getLogger(__name__)

class CognitiveEngine:
    def __init__(self, provider, workspace_root: str | None = None):
        self.provider = provider
        self._workspace_root = (
            os.path.abspath(workspace_root) if workspace_root else os.getcwd()
        )
        self.model = get_model_name()
        self.llm = get_llm_client()
        if not self.llm:
            logger.warning("OPENAI_API_KEY not found. LLM features will be disabled.")

    async def _generate_response(self, messages: list) -> str:
        if not self.llm:
            return "Error: OPENAI_API_KEY not configured."
        try:
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return "Error: LLM request failed. Check API key and network."

    async def get_warnings(self, context: str) -> str:
        """
        Scans the knowledge graph for known problems, bugs, or 'negative diamonds'
        related to the provided context.
        """
        logger.info(f"CognitiveEngine analyzing context for warnings: {context}")
        try:
            res_dict = await self.provider.search(context)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            warnings = []
            
            negative_keywords = ["bug", "error", "problem", "fail", "issue", "time", "broken"]
            
            for r in results:
                if not isinstance(r, dict):
                    continue
                memory_text = r.get("memory", "").lower()
                if any(kw in memory_text for kw in negative_keywords):
                    warnings.append(r.get("memory"))
            
            if warnings:
                formatted = "\n- ".join(warnings)
                return f"PROACTIVE WARNINGS (Spider-Sense triggered):\n- {formatted}"
            return "No immediate warnings for this context."
            
        except Exception as e:
            logger.error(f"Error in get_warnings: {e}")
            return "Unable to retrieve warnings at this time."

    async def generate_tasks(self) -> str:
        """
        Scans the memory for latent intentions, 'to do', 'refactor', and generates a .todo.md file.
        """
        logger.info("CognitiveEngine generating tasks from latent memories...")
        try:
            queries = ["refactor", "to do", "must fix", "should rewrite", "idea"]
            tasks = set()
            for q in queries:
                res_dict = await self.provider.search(q)
                results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    mem = r.get("memory")
                    if mem:
                        tasks.add(mem)
                    
            if not tasks:
                return "No latent tasks found in the subconscious memory."
                
            content = "# Memento Auto-Generated Tasks\n\n*These tasks were automatically crystallized from your subconscious AI memory.*\n\n"
            for t in tasks:
                content += f"- [ ] {t}\n"
                
            filepath = os.path.join(self._workspace_root, "memento.todo.md")
            os.makedirs(self._workspace_root, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            return f"Successfully generated {len(tasks)} tasks in {filepath}"
            
        except Exception as e:
            logger.error(f"Error generating tasks: {e}")
            return f"Error generating tasks: {e}"

    async def evaluate_raw_context(self, raw_text: str, filepath: str = None) -> str:
        """
        Takes raw text (e.g. from a file change) and checks if it closely matches
        any historical bugs or anti-patterns.
        """
        logger.info(f"CognitiveEngine evaluating raw context from daemon for file: {filepath}...")
        try:
            query = f"Known issues or bugs similar to the following text in file {filepath}:\n{raw_text}" if filepath else raw_text
            res_dict = await self.provider.search(query)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            warnings = []
            negative_keywords = ["bug", "error", "problem", "fail", "issue", "time", "broken", "deprecated", "leak"]
            
            for r in results:
                if not isinstance(r, dict):
                    continue
                score = r.get("score", 0.0)
                if score < 0.8:
                    continue
                    
                memory_text = r.get("memory", "").lower()
                if any(kw in memory_text for kw in negative_keywords):
                    warnings.append(r.get("memory"))
            
            if warnings:
                formatted = "\n- ".join(warnings)
                return f"⚠️ SPIDER-SENSE WARNING:\n- {formatted}"
            return ""
            
        except Exception as e:
            logger.error(f"Error evaluating raw context: {e}")
            return ""

    async def detect_latent_features(self, context: str, filepath: str = None) -> str:
        """
        Analyzes the context (e.g., code changes) to proactively propose new features,
        abstractions, or improvements.
        """
        logger.info(f"CognitiveEngine detecting latent features for file: {filepath}...")
        try:
            prompt_data = load_prompt("detect_latent_features")
            
            prompt = prompt_data.get("system_prompt", "")
            
            context_with_filepath = f"File: {filepath}\n\n{context}" if filepath else context
            user_content = prompt_data.get("user_prompt_template", "").format(context_with_filepath=context_with_filepath)
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            
            if "NO PROPOSAL" in llm_response.upper():
                return ""
                
            return f"💡 [FEATURE PROPOSAL]\n\n{llm_response}"
        except Exception as e:
            logger.error(f"Error detecting latent features: {e}")
            return ""

    async def synthesize_dreams(self, context: str = None) -> str:
        logger.info(f"CognitiveEngine entering Dream State. Context: {context}")
        try:
            query = context if context else "general architecture decisions"
            res_dict = await self.provider.search(query, limit=20)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            if not results:
                return "[DRAFT_INSIGHT] Not enough memories to start the Dream State."
                
            memory_list = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                mem_id = r.get("id", "unknown")
                mem_text = r.get("memory", "")
                memory_list.append(f"- ID: {mem_id} | Fact: {mem_text}")
                
            memories_str = "\n".join(memory_list)
            
            prompt_data = load_prompt("synthesize_dreams")
            
            prompt = prompt_data.get("system_prompt", "").format(memories_str=memories_str)
            user_content = prompt_data.get("user_prompt_template", "")
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            return f"🌌 [DRAFT_INSIGHT] Synthesis Generated:\n\n{llm_response}\n\n*(Use memento_add_memory to crystallize this insight in the Knowledge Graph if you deem it valid)*"
            
        except Exception as e:
            logger.error(f"Error during Dream State synthesis: {e}")
            return f"[DRAFT_INSIGHT] Error during synthesis: {str(e)}"

    async def check_goal_alignment(self, code_or_plan: str, context: str = "") -> str:
        logger.info("CognitiveEngine checking goal alignment...")
        try:
            ctx_param = context.strip() if isinstance(context, str) and context.strip() else None
            goal_rows = await self.provider.list_goals(
                context=ctx_param, active_only=True, limit=20
            )

            if not goal_rows:
                return "[GOAL ALIGNMENT] No active goals found in memory for comparison."

            goals = [r.get("goal") for r in goal_rows if isinstance(r, dict) and r.get("goal")]
            if not goals:
                return "[GOAL ALIGNMENT] No active goals found in memory for comparison."

            goals_str = "\n- ".join(goals)
            
            prompt_data = load_prompt("check_goal_alignment")
            
            prompt = prompt_data.get("system_prompt", "").format(goals_str=goals_str)
            user_content = prompt_data.get("user_prompt_template", "").format(code_or_plan=code_or_plan)
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            return f"🛡️ [GOAL ALIGNMENT]\n\n{llm_response}"
        except Exception as e:
            logger.error(f"Error checking alignment: {e}")
            return f"[GOAL ALIGNMENT] Error during validation: {str(e)}"

    async def parse_natural_language_intent(self, query: str) -> dict:
        """
        Universal Router: Parses a natural language string and extracts the 
        intended action and parameters as a structured JSON dict.
        """
        logger.info(f"CognitiveEngine parsing intent for: {query}")
        try:
            prompt_data = load_prompt("parse_natural_language_intent")
                
            prompt = prompt_data.get("system_prompt", "")
            user_content = prompt_data.get("user_prompt_template", "").format(query=query)
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            
            cleaned = llm_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
                
            parsed = json.loads(cleaned.strip())
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return {"action": "UNKNOWN", "payload": {}}
