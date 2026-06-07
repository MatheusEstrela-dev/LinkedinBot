# LinkedIn Job Matcher Bot

Monitora vagas no LinkedIn e envia as que melhor combinam com seu perfil via Telegram.

## Configuração

### 1. Instalar dependências
```bash
uv sync
uv run playwright install chromium
```

### 2. Configurar variáveis de ambiente
```bash
cp .env.example .env
# edite .env com seu TELEGRAM_TOKEN e TELEGRAM_CHAT_ID
```

**Como obter o token do Telegram:**
1. Abra @BotFather no Telegram
2. `/newbot` → siga as instruções → copie o token
3. Mande uma mensagem ao seu bot e acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` para pegar seu `chat_id`

### 3. Editar seu perfil
Edite `config/profile.json` com suas skills, cargo desejado, senioridade e localização.

```json
{
  "skills": ["Python", "FastAPI", "Docker"],
  "target_roles": ["Backend Developer", "Python Developer"],
  "seniority": "pleno",
  "location": "Belo Horizonte",
  "accept_remote": true,
  "min_salary": 5000,
  "max_salary": 12000,
  "min_score": 50
}
```

## Uso

**Rodar uma vez (testar):**
```bash
uv run python main.py --once
```

**Rodar em loop a cada 4 horas:**
```bash
uv run python main.py
```

**Rodar a cada 2 horas:**
```bash
uv run python main.py --interval 2
```

## Como funciona o score (0–100)

| Critério           | Peso | Lógica                                            |
|--------------------|------|---------------------------------------------------|
| Skills técnicas    | 40   | % das suas skills encontradas na descrição × 40   |
| Senioridade/cargo  | 30   | Título bate? Exato=30, nível adjacente=15, não=0  |
| Localização/remoto | 20   | Remoto ou cidade correta = 20                     |
| Salário            | 10   | Dentro da faixa = 10, não informado = 5 (neutro)  |

Vagas com score abaixo de `min_score` (padrão: 50) são ignoradas.

## Estrutura do projeto
```
LinkedinBot/
├── config/profile.json   # Seu perfil
├── data/jobs.db          # SQLite (criado automaticamente)
├── src/
│   ├── scraper.py        # Coleta vagas do LinkedIn
│   ├── matcher.py        # Calcula score de compatibilidade
│   ├── notifier.py       # Envia mensagem no Telegram
│   └── database.py       # Deduplicação e histórico
├── main.py               # Entry point
└── requirements.txt
```
