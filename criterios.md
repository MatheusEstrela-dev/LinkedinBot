# Critérios do bot — como as vagas são buscadas, pontuadas e enviadas

Este documento explica, em linguagem simples, o que o código faz em cada etapa.
Tudo o que é configurável fica em [`config/profile.json`](config/profile.json).

---

## 1. Fluxo geral

```
GitHub Actions (9h07, 15h07, 21h07 de Brasília)
        │
        ▼
main.py ──► scraper.py ──► busca vagas no LinkedIn
        │                    ├─ API pública do LinkedIn (guest_scraper.py) — sem login
        │                    └─ busca internacional (se "international.enabled")
        ▼
   para cada vaga:
        ├─ já foi enviada antes? (data/jobs.db) ──► sim: ignora
        ├─ calcula o score (matcher.py, 0 a 100)
        └─ score ≥ min_score? ──► sim: salva no banco + envia no Telegram (notifier.py)
```

| Arquivo | Papel |
|---|---|
| `main.py` | Orquestra tudo (pipeline). |
| `src/scraper.py` | Monta as buscas e junta os resultados. |
| `src/guest_scraper.py` | Busca pela API pública do LinkedIn (sem login, sem navegador). |
| `src/matcher.py` | **Regras de pontuação (match).** |
| `src/database.py` | Guarda as vagas já enviadas, para não repetir. |
| `src/notifier.py` | Monta e envia a mensagem no Telegram, e envia alertas. |
| `src/auth.py` | Login com e-mail/senha (só usado se `browser_scraper` estiver ligado). |

> O scraper com navegador + cookie `li_at` está **desligado** por padrão: o LinkedIn
> derruba o cookie quando ele é usado pelos servidores do GitHub. Para religar,
> coloque `"browser_scraper": true` no `profile.json` (aí volta o aviso de cookie expirado).

---

## 2. Quais vagas são buscadas

Para cada item de `target_roles` (ex.: `"PYTHON"`, `"Desenvolvedor PHP Laravel"`,
`"Full Stack Developer"`), o bot pesquisa no LinkedIn com estes filtros:

| Filtro | Valor | De onde vem |
|---|---|---|
| Local | `Brazil` (ou a cidade, se `accept_remote` for `false`) | `location`, `accept_remote` |
| Período | Última semana | fixo no código |
| Senioridade | pleno → "Pleno-sênior" do LinkedIn | `seniority` |
| Modalidade | Remoto + Híbrido (se `accept_remote: true`) | `accept_remote` |
| Quantidade | até 25 vagas por cargo | fixo no código |

Mapeamento de senioridade (filtro do LinkedIn):

| `seniority` | Filtro aplicado |
|---|---|
| `junior` | Estágio + Assistente/Júnior |
| `pleno` | Pleno-sênior |
| `senior` | Pleno-sênior + Diretor |

### Vagas internacionais

Se `international.enabled` for `true`, o bot faz uma busca extra:

- Cargos em inglês: `international.roles` (ex.: `"Python Developer"`, `"Laravel Developer"`).
- Locais: `international.locations` (ex.: `"Worldwide"`, `"Latin America"`).
- **Somente vagas 100% remotas**: a vaga precisa citar remote/remoto/teletrabajo/télétravail
  e não pode citar hybrid/híbrido (a API às vezes ignora o filtro de remoto).
- Até `international.limit` vagas por combinação cargo × local.
- No Telegram aparecem com a etiqueta **🌎 Internacional (remoto)** e o
  **🗣 idioma** da vaga (Inglês, Espanhol, Francês, Alemão, Italiano ou Português).
  O idioma é estimado contando palavras comuns de cada língua no título + descrição;
  sem descrição, aparece "Não identificado".

---

## 3. Regras de match (pontuação de 0 a 100)

O score é a soma de 4 critérios. Código: [`src/matcher.py`](src/matcher.py).

| Critério | Máximo | Resumo |
|---|---:|---|
| Skills | **40** | % das suas skills que aparecem na vaga |
| Senioridade | **30** | nível detectado no título bate com o seu |
| Localização | **20** | remoto ou na sua cidade |
| Salário | **10** | faixa da vaga cruza com a sua |
| **Total** | **100** | |

### 3.1 Skills — até 40 pontos

- Procura cada skill de `skills` no **título + descrição** da vaga (sem diferenciar maiúsculas).
- A busca é por **palavra inteira**: `"Go"` casa com "Go", mas não com "Google".
- Fórmula:

  ```
  pontos = arredondar( (skills encontradas ÷ total de skills do perfil) × 40 )
  ```

- Hoje o perfil tem **18 skills**, então cada skill encontrada vale ≈ **2,2 pontos**.
  Ex.: vaga cita 9 das 18 → 9/18 × 40 = **20 pontos**.
- A mensagem do Telegram mostra ✅ as skills encontradas e ❌ as que faltaram.

> 💡 Quanto **mais** skills no perfil, **mais difícil** é pontuar alto aqui, porque
> nenhuma vaga cita todas. Manter só as skills que importam aumenta os scores.

### 3.2 Senioridade — até 30 pontos

Olha **só o título** da vaga e procura estas palavras (nesta ordem; vale a primeira que achar):

| Nível detectado | Palavras procuradas |
|---|---|
| junior | junior, júnior, jr, entry, estágio, trainee, intern |
| pleno | pleno, mid, middle, ii, " 2 " |
| senior | senior, sênior, sr, lead, staff, principal, architect, especialista |

Pontuação (seu `seniority` = `pleno`):

| Situação | Pontos |
|---|---:|
| Nível igual ao seu | **30** |
| Nível vizinho (para pleno: júnior ou sênior) | **15** |
| Título não indica nível | **15** (neutro) |
| Nível distante (ex.: júnior quando você é sênior) | **0** |

> ⚠️ A busca é por **trecho de texto**, não palavra inteira. Ex.: "**lead**er"
> conta como sênior e "**mid**ia" conta como pleno. Raro, mas acontece.

### 3.3 Localização — até 20 pontos

| Situação | Pontos |
|---|---:|
| Vaga marcada como remota | **20** |
| Local da vaga contém sua cidade (`location`, ex.: "Belo Horizonte") | **20** |
| Local contém "remote"/"remoto" e `accept_remote` é `true` | **20** |
| Nenhum dos casos | **0** |

Uma vaga é marcada como **remota** se o local **ou a descrição** contiver
`remote`, `remoto`, `home office` ou `anywhere`. Vagas internacionais são sempre remotas.

### 3.4 Salário — até 10 pontos

O salário é lido da descrição, só nestes formatos:
`R$ 5.000 - R$ 8.000`, `R$ 5.000 a R$ 8.000`, `5.000 – 8.000 BRL/reais`.

| Situação | Pontos |
|---|---:|
| Faixa da vaga cruza com `min_salary`–`max_salary` (5.000–9.000) | **10** |
| Vaga não informa salário (a maioria) | **5** (neutro) |
| Faixa totalmente fora da sua | **0** |

> Salários em dólar/euro (vagas internacionais) não são lidos → ficam com 5 (neutro).

---

## 4. Quem recebe notificação

- Só vagas com **score ≥ `min_score`** (hoje **50**) vão para o Telegram.
- Cada vaga enviada é salva em `data/jobs.db` e **nunca é reenviada**.
  Conta como a mesma vaga: mesmo ID **ou** mesmo título + empresa (empresas que
  repostam a vaga em vários países com IDs diferentes).
  O banco é mantido entre execuções pelo cache do GitHub Actions.
- Vagas abaixo do corte **não** são salvas (são reavaliadas na próxima busca,
  mas o score tende a ser o mesmo).

### Exemplo de cálculo

> **"Desenvolvedor Fullstack Pleno"** — remota, sem salário, descrição cita
> PHP, Laravel, JavaScript, HTML, CSS, SQL, Git, Docker (8 das 18 skills)

| Critério | Conta | Pontos |
|---|---|---:|
| Skills | 8/18 × 40 = 17,8 | 18 |
| Senioridade | "pleno" no título = igual ao seu | 30 |
| Localização | remota | 20 |
| Salário | não informado | 5 |
| **Total** | | **73 → enviada** ✅ |

### Faixas práticas

| Score | Interpretação |
|---|---|
| 70+ | Match forte (nível certo, remota/BH e várias skills em comum) |
| 50–69 | Match razoável — **enviada** |
| < 50 | Descartada (geralmente nível errado ou poucas skills) |

> Um detalhe: uma vaga **sênior**, remota, sem salário, ganha 15 + 20 + 5 = 40
> só de base. Bastam ~5 skills em comum (11 pts) para passar dos 50.

---

## 5. Alertas no Telegram

Além das vagas, o bot manda **⚠️ aviso** quando:

- A busca terminou com **0 vagas** → veja o log em *Actions* no GitHub.

---

## 6. Como ajustar (cola rápida)

Tudo em `config/profile.json`:

| Quero… | Mude |
|---|---|
| Receber mais vagas | diminua `min_score` (ex.: 40) |
| Receber só as melhores | aumente `min_score` (ex.: 65) |
| Buscar outros cargos | edite `target_roles` |
| Pontuar mais alto em skills | deixe em `skills` só o que é essencial |
| Mudar faixa salarial | `min_salary` / `max_salary` |
| Limitar o tempo da busca (padrão 15 min) | `search_budget_minutes` |
| Desligar vagas internacionais | `"international": { "enabled": false }` |
| Mudar países/regiões internacionais | `international.locations` (ex.: `"United States"`, `"European Union"`) |

Horários de execução: `.github/workflows/bot.yml`, linha `cron`
(o horário é em **UTC** — Brasília = UTC − 3; roda no minuto 7 para evitar a sobrecarga do GitHub no início da hora).
