import logging
import os
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class CognitiveEngine:
    """
    The Cognitive Engine for Memento.
    Analyzes the KnowledgeGraph in background or proactively to generate insights.
    """
    def __init__(self, provider):
        self.provider = provider
        
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        self.model = os.environ.get("MEM0_MODEL", "openai/gpt-4o-mini")
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not found. LLM features will be disabled.")
            self.llm = None
        else:
            self.llm = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def _generate_response(self, messages: list) -> str:
        if not self.llm:
            return "Errore: OPENAI_API_KEY non configurata."
        try:
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return f"Errore LLM: {str(e)}"

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
                return "No latent tasks found in the subconsciuos memory."
                
            content = "# Memento Auto-Generated Tasks\n\n*These tasks were automatically crystallized from your subconscious AI memory.*\n\n"
            for t in tasks:
                content += f"- [ ] {t}\n"
                
            filepath = os.path.join(os.getcwd(), "memento.todo.md")
            with open(filepath, "w") as f:
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
            query = f"Problemi noti o bug simili al seguente testo nel file {filepath}:\n{raw_text}" if filepath else raw_text
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
            import json
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "detect_latent_features.json")
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_data = json.load(f)
            
            prompt = prompt_data.get("system_prompt", "")
            
            context_with_filepath = f"File: {filepath}\n\n{context}" if filepath else context
            user_content = prompt_data.get("user_prompt_template", "").format(context_with_filepath=context_with_filepath)
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            
            if "NESSUNA PROPOSTA" in llm_response.upper():
                return ""
                
            return f"💡 [PROPOSTA FUNZIONALITÀ]\n\n{llm_response}"
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
                return "[DRAFT_INSIGHT] Non ci sono abbastanza ricordi per avviare il Dream State."
                
            memory_list = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                mem_id = r.get("id", "unknown")
                mem_text = r.get("memory", "")
                memory_list.append(f"- ID: {mem_id} | Fatto: {mem_text}")
                
            memories_str = "\n".join(memory_list)
            
            import json
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "synthesize_dreams.json")
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_data = json.load(f)
            
            prompt = prompt_data.get("system_prompt", "").format(memories_str=memories_str)
            user_content = prompt_data.get("user_prompt_template", "")
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            return f"🌌 [DRAFT_INSIGHT] Sintesi Generata:\n\n{llm_response}\n\n*(Usa memento_add_memory per cristallizzare questa intuizione nel Knowledge Graph se la ritieni valida)*"
            
        except Exception as e:
            logger.error(f"Error during Dream State synthesis: {e}")
            return f"[DRAFT_INSIGHT] Errore durante la sintesi: {str(e)}"

    async def check_goal_alignment(self, code_or_plan: str, context: str = "") -> str:
        logger.info("CognitiveEngine checking goal alignment...")
        try:
            search_query = f"obiettivo goal per il contesto: {context}" if context else "obiettivo goal"
            res_dict = await self.provider.search(search_query, limit=5)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            if not results:
                return "[ALLINEAMENTO GOAL] Nessun obiettivo attivo trovato in memoria per il confronto."
                
            goals = [r.get("memory") for r in results if isinstance(r, dict)]
            goals_str = "\n- ".join(goals)
            
            import json
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "check_goal_alignment.json")
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_data = json.load(f)
            
            prompt = prompt_data.get("system_prompt", "").format(goals_str=goals_str)
            user_content = prompt_data.get("user_prompt_template", "").format(code_or_plan=code_or_plan)
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ]
            
            llm_response = await self._generate_response(messages)
            return f"🛡️ [ALLINEAMENTO GOAL]\n\n{llm_response}"
        except Exception as e:
            logger.error(f"Error checking alignment: {e}")
            return f"[ALLINEAMENTO GOAL] Errore durante la validazione: {str(e)}"

    async def parse_natural_language_intent(self, query: str) -> dict:
        """
        Universal Router: Parses a natural language string and extracts the 
        intended action and parameters as a structured JSON dict.
        """
        logger.info(f"CognitiveEngine parsing intent for: {query}")
        try:
            import json
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "parse_natural_language_intent.json")
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_data = json.load(f)
                
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
