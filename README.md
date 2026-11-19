# ⚡ ProspectFlow

**Mini-CRM para prospecção ativa via WhatsApp** — feito para quem vende criação de sites para pequenos negócios locais (barbearias, pet shops, oficinas…).

Importe a planilha de leads do Google Maps, deixe o ProspectFlow priorizar quem tem mais chance de fechar, e siga a fila do dia: um clique copia a mensagem personalizada e abre o WhatsApp, outro registra o envio e avança o funil. Follow-ups, sugestões de perda e lembretes de cobrança aparecem sozinhos.

> 📸 _Screenshots_: adicione em `docs/` e referencie aqui.
>
> | Hoje | Funil | Dashboard |
> |---|---|---|
> | `docs/hoje.png` | `docs/funil.png` | `docs/dashboard.png` |

---

## ✨ Funcionalidades

**Importação inteligente**
- Arraste um `.xlsx` ou `.csv`; as colunas são **mapeadas automaticamente** (com ajuste manual).
- Pré-visualização linha a linha: **novos**, **duplicados** e **com erro**, antes de gravar.
- Normalização: telefone no padrão `55DDDNÚMERO` (validando DDD da Anatel), nomes, cidade/bairro, nota e nº de avaliações.
- Duplicados por **telefone** ou **nome + cidade** (inclusive dentro do próprio arquivo), com opção de ignorar ou atualizar.
- **Classificação de nicho** por palavras-chave na categoria e no nome.
- Relatório final da importação.

**Rotina diária (tela Hoje)**
- Cada dia da semana tem um nicho; a fila traz os **10 leads de maior score** dele (meta configurável) + **follow-ups vencidos**.
- **Copiar + WhatsApp**: copia a mensagem do template e abre `wa.me` com o texto já preenchido.
- **Enviei**: registra a interação e avança o status no funil.
- Follow-up após 2 dias sem resposta; depois de 3 follow-ups, sugere marcar como perdido.
- Lembretes de **mensalidade** dos clientes recorrentes, com "Marcar pago".

**Funil e leads**
- Kanban com **arrastar e soltar**: Novo → Abordado → Respondeu → Aceitou prévia → Prévia enviada → Proposta → Fechado | Perdido.
- Ao fechar, escolhe o plano (**R$ 497 à vista** ou **R$ 297 + R$ 49/mês**); ao perder, registra o motivo.
- Lista de leads com busca, filtros persistentes, edição, ações em massa e **exportação CSV/Excel**.
- Linha do tempo de cada lead (interações + mudanças de status).

**Dashboard**
- Abordagens por dia/semana, taxas de **resposta, prévia e fechamento por nicho**, funil de conversão, ranking de nichos, faturamento mensal e **MRR**.

**Configurações**
- Nichos (dia da semana, cor, palavras-chave), templates por etapa com **prévia ao vivo** e validação de variáveis (`{nome}`, `{empresa}`, `{servico}`, `{cidade}`), metas e pesos do score.

**Interface**
- Visual SaaS (inspirado em Linear/Vercel), modo claro/escuro, sidebar fixa, badges coloridos, toasts em todas as ações, estados vazios e layout responsivo.

## 🧮 Score de prioridade (0–100)

| Critério | Peso padrão | Regra |
|---|---|---|
| Nota no Google | 40 | linear até 5,0 |
| Nº de avaliações | 30 | escala logarítmica até 500 |
| Site | 30 | sem site = 30 · site ruim/só rede social = 20 · tem site = 0 |

Bem avaliado, com muitas avaliações e **sem site** = cliente ideal. Os pesos são editáveis em Configurações.

## 🏗️ Arquitetura

```
app/
├── models/         # SQLAlchemy 2.0 (Lead, Niche, Interaction, StatusHistory, Sale, Payment, …)
├── repositories/   # consultas reutilizáveis (filtros, deduplicação, configurações)
├── services/       # regras de negócio puras e testáveis
│   ├── importing/  # leitura, mapeamento de colunas, normalização, dedupe, classificação
│   ├── funnel.py   # transições de status, vendas, follow-up
│   ├── daily_queue.py · followup.py · billing.py · metrics.py · templates.py · score.py
├── ui/             # NiceGUI: layout, componentes e páginas
├── scheduler.py    # APScheduler: gera mensalidades vencidas a cada hora
└── main.py
scripts/            # seed de demonstração e geração das planilhas de exemplo
samples/            # leads_exemplo.xlsx / .csv (com duplicados e erros de propósito)
tests/              # pytest: regras de negócio + testes de interface (navegador simulado)
```

**Decisões principais**
- A UI não contém regra de negócio: tudo passa por `services/`, que recebem uma `Session` e são testados com SQLite em memória.
- Conversões do dashboard usam o **histórico de status** — um lead perdido depois de responder continua contando como "respondeu".
- O Kanban usa SortableJS só para o gesto; o servidor valida a mudança e redesenha o quadro, então a tela nunca mostra algo que não foi salvo.

## 🛠️ Stack

Python 3.11+ · [NiceGUI](https://nicegui.io) (Vue/Quasar + Tailwind) · SQLAlchemy 2 + SQLite · Pandas + openpyxl · ECharts · APScheduler · Pydantic Settings · Pytest

## 🚀 Como rodar

```bash
git clone <repo> && cd prospectflow
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # opcional: ajuste DDD padrão, porta, fuso…

python -m scripts.seed --reset  # opcional: 175 leads fictícios para explorar
python -m app.main              # http://127.0.0.1:8080
```

Para testar a importação sem planilha própria, use **Importar → "Usar planilha de exemplo"** (ou os arquivos em `samples/`).

### Configuração (`.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `PF_DATABASE_URL` | `sqlite:///data/prospectflow.db` | banco de dados |
| `PF_TIMEZONE` | `America/Sao_Paulo` | fuso para "hoje", follow-ups e cobranças |
| `PF_DEFAULT_DDD` | `11` | DDD aplicado a telefones sem DDD |
| `PF_HOST` / `PF_PORT` | `127.0.0.1` / `8080` | servidor |
| `PF_STORAGE_SECRET` | — | segredo das preferências do navegador (tema, filtros) |

## ✅ Testes

```bash
python -m pytest
```

Cobrem importação (normalização, mapeamento, dedupe, classificação), score, funil, follow-up, fila do dia, cobrança, métricas, exportação e as telas principais via `nicegui.testing.User`.

## 📄 Licença

MIT
