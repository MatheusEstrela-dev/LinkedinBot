import logging
import os

logger = logging.getLogger(__name__)


def ask_claude(question: str, jobs_context: str = "") -> str:
    """Ask Claude about jobs/career. Returns a text response in Portuguese."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return (
            "⚠️ ANTHROPIC_API_KEY não configurada.\n"
            "Adicione esta variável no seu .env local ou nos GitHub Secrets do repositório."
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        user_content = question
        if jobs_context:
            user_content = (
                f"Vagas recentes encontradas pelo bot:\n\n{jobs_context}\n\n"
                f"Pergunta: {question}"
            )

        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            system=(
                "Você é um assistente de carreira especializado em análise de vagas de emprego para desenvolvedores. "
                "O usuário é Matheus, desenvolvedor Full Stack com experiência em PHP, Laravel, Python, "
                "PostgreSQL e outras tecnologias, baseado em Belo Horizonte. "
                "Analise as vagas fornecidas e ajude-o a tomar boas decisões sobre sua carreira. "
                "Seja direto, prático e conciso. Responda sempre em português do Brasil."
            ),
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text
    except Exception as e:
        logger.error("Erro ao chamar Claude API: %s", e)
        return f"❌ Erro ao consultar Claude: {e}"
