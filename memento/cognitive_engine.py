import logging
import os
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class CognitiveEngine:
    """
    The Cognitive Engine for Memento.
    Analyzes the KnowledgeGraph in background or proactively to generate insights.
    """
    def __init__(self, provider):
        self.provider = provider
        
        import os
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        self.model = os.environ.get("MEM0_MODEL", "openai/gpt-4o-mini")
        self.llm = OpenAI(api_key=api_key, base_url=base_url)

    def _generate_response(self, messages: list) -> str:
        try:
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"LLM Error: {e}")
            return f"Errore LLM: {str(e)}"


    def get_warnings(self, context: str) -> str:
        """
        Scans the knowledge graph for known problems, bugs, or 'negative diamonds'
        related to the provided context.
        """
        logger.info(f"CognitiveEngine analyzing context for warnings: {context}")
        # In a real implementation, we would query the KG for entities matching context
        # and look for negative predicates.
        # For this prototype, we'll do a semantic search using the provider
        # and filter for negative keywords.
        try:
            res_dict = self.provider.search(context)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            warnings = []
            
            negative_keywords = ["bug", "error", "problem", "fail", "issue", "time", "broken"]
            
            for r in results:
                if not isinstance(r, dict): continue
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

    def generate_tasks(self) -> str:
        """
        Scans the memory for latent intentions, 'to do', 'refactor', and generates a .todo.md file.
        """
        logger.info("CognitiveEngine generating tasks from latent memories...")
        try:
            # We search for tasks-related keywords
            queries = ["refactor", "to do", "must fix", "should rewrite", "idea"]
            tasks = set()
            for q in queries:
                res_dict = self.provider.search(q)
                results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
                for r in results:
                    if not isinstance(r, dict): continue
                    mem = r.get("memory")
                    if mem: tasks.add(mem)
                    
            if not tasks:
                return "No latent tasks found in the subconsciuos memory."
                
            content = "# Memento Auto-Generated Tasks\n\n*These tasks were automatically crystallized from your subconscious AI memory.*\n\n"
            for t in tasks:
                content += f"- [ ] {t}\n"
                
            # Write to workspace
            filepath = os.path.join(os.getcwd(), "memento.todo.md")
            with open(filepath, "w") as f:
                f.write(content)
                
            return f"Successfully generated {len(tasks)} tasks in {filepath}"
            
        except Exception as e:
            logger.error(f"Error generating tasks: {e}")
            return f"Error generating tasks: {e}"

    def evaluate_raw_context(self, raw_text: str) -> str:
        """
        Takes raw text (e.g. from a file change) and checks if it closely matches
        any historical bugs or anti-patterns.
        """
        logger.info("CognitiveEngine evaluating raw context from daemon...")
        try:
            res_dict = self.provider.search(raw_text)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            warnings = []
            negative_keywords = ["bug", "error", "problem", "fail", "issue", "time", "broken", "deprecated", "leak"]
            
            for r in results:
                if not isinstance(r, dict): continue
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


    def detect_latent_features(self, context: str) -> str:
        """
        Analyzes the context (e.g., code changes) to proactively propose new features,
        abstractions, or improvements.
        """
        logger.info("CognitiveEngine detecting latent features...")
        try:
            prompt = (
                "Sei l'Assistente Architetturale Proattivo di Memento. Analizza il seguente codice o testo "
                "e proponi UNA singola, potente e utile funzionalità latente, astrazione o miglioramento "
                "che lo sviluppatore potrebbe implementare. "
                "Se il codice non suggerisce alcuna nuova funzionalità ovvia o è troppo banale, rispondi ESATTAMENTE con 'NESSUNA PROPOSTA'. "
                "Altrimenti, descrivi la proposta in modo conciso e orientato all'azione."
            )
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Contesto da analizzare:\n\n{context}"}
            ]
            
            llm_response = self._generate_response(messages)
            
            if "NESSUNA PROPOSTA" in llm_response.upper():
                return ""
                
            return f"💡 [PROPOSTA FUNZIONALITÀ]\n\n{llm_response}"
        except Exception as e:
            logger.error(f"Error detecting latent features: {e}")
            return ""

    def synthesize_dreams(self, context: str = None) -> str:
        logger.info(f"CognitiveEngine entering Dream State. Context: {context}")
        try:
            query = context if context else "general architecture decisions"
            res_dict = self.provider.search(query, limit=20)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            if not results:
                return "[DRAFT_INSIGHT] Non ci sono abbastanza ricordi per avviare il Dream State."
                
            memory_list = []
            for r in results:
                if not isinstance(r, dict): continue
                mem_id = r.get("id", "unknown")
                mem_text = r.get("memory", "")
                memory_list.append(f"- ID: {mem_id} | Fatto: {mem_text}")
                
            memories_str = "\n".join(memory_list)
            
            prompt = (
                "Sei Memento in 'Dream State' (Stato di Sogno). Il tuo obiettivo è analizzare i seguenti "
                "fatti disconnessi estratti dalla memoria a lungo termine. Trova un pattern nascosto, "
                "una contraddizione, o una lezione architetturale. Genera UNA singola e potente "
                "intuizione (Synthetic Diamond). DEVI citare esplicitamente i Memory ID che hanno "
                "generato questa intuizione. Se non vedi pattern chiari, rispondi 'Nessuna sintesi valida'.\n\n"
                f"Memorie:\n{memories_str}"
            )
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Avvia la sintesi dei sogni."}
            ]
            
            llm_response = self._generate_response(messages)
            return f"🌌 [DRAFT_INSIGHT] Sintesi Generata:\n\n{llm_response}\n\n*(Usa memento_add_memory per cristallizzare questa intuizione nel Knowledge Graph se la ritieni valida)*"
            
        except Exception as e:
            logger.error(f"Error during Dream State synthesis: {e}")
            return f"[DRAFT_INSIGHT] Errore durante la sintesi: {str(e)}"


    def check_goal_alignment(self, code_or_plan: str) -> str:
        logger.info("CognitiveEngine checking goal alignment...")
        try:
            res_dict = self.provider.search("obiettivo goal", limit=5)
            results = res_dict.get("results", []) if isinstance(res_dict, dict) else res_dict
            
            if not results:
                return "[ALLINEAMENTO GOAL] Nessun obiettivo attivo trovato in memoria per il confronto."
                
            goals = [r.get("memory") for r in results if isinstance(r, dict)]
            goals_str = "\n- ".join(goals)
            
            prompt = (
                "Sei il 'Strict Mentor' di Memento. Valuta in modo severo il seguente codice o piano "
                "rispetto a questi obiettivi fondamentali del progetto:\n"
                f"- {goals_str}\n\n"
                "Se il codice è banale, non innovativo o viola chiaramente gli obiettivi, rispondi "
                "con '❌ BOCCIATO' spiegando perché e cosa manca per raggiungere l'eccellenza richiesta. "
                "Se il codice è allineato e spinge l'innovazione, rispondi con '✅ APPROVATO'."
            )
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Valuta questo lavoro:\n\n{code_or_plan}"}
            ]
            
            llm_response = self._generate_response(messages)
            return f"🛡️ [ALLINEAMENTO GOAL]\n\n{llm_response}"
        except Exception as e:
            logger.error(f"Error checking alignment: {e}")
            return f"[ALLINEAMENTO GOAL] Errore durante la validazione: {str(e)}"


    def parse_natural_language_intent(self, query: str) -> dict:
        """
        Universal Router: Parses a natural language string and extracts the 
        intended action and parameters as a structured JSON dict.
        """
        logger.info(f"CognitiveEngine parsing intent for: {query}")
        try:
            prompt = (
                "Sei il Router Universale di Memento. Analizza la richiesta dell'utente "
                "e classificala in una delle seguenti azioni. DEVI rispondere ESCLUSIVAMENTE "
                "con un oggetto JSON valido, senza testo aggiuntivo o formattazione markdown. "
                "Puoi estrarre un campo opzionale 'focus_area' se la richiesta indica un contesto "
                "specifico (es. 'Cerca bug nel frontend' -> focus_area: 'frontend').\n\n"
                "Azioni disponibili:\n"
                "1. 'ADD': L'utente vuole memorizzare un'informazione. Payload richiesto: {'text': 'informazione da salvare'}\n"
                "2. 'SEARCH': L'utente fa una domanda o cerca un'informazione specifica. Payload richiesto: {'query': 'concetto chiave da cercare'}\n"
                "3. 'LIST': L'utente chiede di vedere tutte le memorie o un riepilogo generale. Payload richiesto: {}\n"
                "4. 'DREAM': L'utente chiede idee, intuizioni o sintesi. Payload richiesto: {'context': 'argomento (opzionale)'}\n"
                "5. 'ALIGNMENT': L'utente chiede di valutare o controllare un codice/piano. Payload richiesto: {'content': 'il codice o piano'}\n"
                "6. 'UNKNOWN': Richiesta non comprensibile. Payload richiesto: {}\n\n"
                "Schema JSON di output desiderato:\n"
                "{\n"
                "  \"action\": \"ADD|SEARCH|LIST|DREAM|ALIGNMENT|UNKNOWN\",\n"
                "  \"payload\": { ... },\n"
                "  \"focus_area\": \"eventuale area di contesto, opzionale\"\n"
                "}\n\n"
                "Esempio risposta:\n"
                "{\"action\": \"SEARCH\", \"payload\": {\"query\": \"bug\"}, \"focus_area\": \"frontend\"}"
            )
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": query}
            ]
            
            llm_response = self._generate_response(messages)
            
            cleaned = llm_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
                
            import json
            parsed = json.loads(cleaned.strip())
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return {"action": "UNKNOWN", "payload": {}}
