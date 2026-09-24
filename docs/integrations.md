# Integrações e validação

Documentação oficial consultada em 23/09/2026. Os adaptadores têm testes offline com `httpx.MockTransport`; isso verifica validação de requisições e respostas simuladas, não acesso de conta real.

## Alpaca

### Ordens paper

- Origem fixa: `https://paper-api.alpaca.markets`. O adaptador rejeita outra origem, esquema HTTP, porta, credenciais embutidas, caminho ou query antes de requisitar; redirects são recusados e TLS é verificado.
- Implementado em `apps/api/paperlab/alpaca.py`: leitura de conta, ativos, posições, ordens e atividades de fill; consulta por `client_order_id`; cancelamento; envio de ordem market crypto em `GTC`; proteção de timeout por consulta do ID sem reenvio cego; normalização dos estados conhecidos.
- O preflight é somente de leitura. Requer três conjuntos A/B/C, IDs de conta diferentes, estado ativo, BTC/USD negociável, nenhuma posição/ordem aberta e equivalência de caixa e patrimônio em até USD 0,01. Devolve mínimo e incrementos publicados do ativo. Nenhuma conta é alterada.
- Payloads aceitam BTC/USD e ETH/USD. BTC é o único habilitado por padrão. A interface ainda não inicia ordens e o cliente não está conectado ao worker.

### Dados e notícias

- Origem separada: `https://data.alpaca.markets`. Candles usam `/v1beta3/crypto/us/bars`, timeframe `1Hour`, paginação, deduplicação/ordenação e remoção de candle ainda aberto.
- Notícias usam `/v1beta1/news`, sem conteúdo integral por padrão. Símbolo de ordem BTC/USD mapeia para símbolo de notícias BTCUSD.
- O cliente devolve notícias/candles para chamadas diretas, mas ainda não as grava como snapshots PAPER no worker. Saúde vazia versus falha HTTP deve continuar distinta quando o pipeline for conectado.

### Evidência de validação

**Integração externa não executada.** Não havia credenciais autorizadas disponíveis nesta entrega. Nenhuma conta foi acessada e nenhuma ordem paper foi enviada. Cobertura mock inclui host não paper, redirect, timeout/consulta por ID, deduplicação de candles, corte de barra aberta, mapeamento/ausência de notícias, status desconhecido e preflight de IDs/saldos.

Referências oficiais conferidas:

- [Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading)
- [Crypto Trading](https://docs.alpaca.markets/us/docs/crypto-trading)
- [Working with Orders](https://docs.alpaca.markets/us/docs/working-with-orders)
- [Consulta por client_order_id](https://docs.alpaca.markets/us/reference/getorderbyclientorderid)
- [Barras cripto](https://docs.alpaca.markets/us/reference/cryptobars-1)
- [Historical News Data](https://docs.alpaca.markets/us/docs/historical-news-data)
- [News API](https://docs.alpaca.markets/us/reference/news-3)

## OpenRouter e JEV

- Cliente generativo: `POST https://openrouter.ai/api/v1/chat/completions`, resposta `json_schema` estrita, provedor precisa aceitar parâmetros obrigatórios, fallback automático desabilitado. O validador consulta a ficha de endpoints do ID de modelo e exige anúncio de `structured_outputs`.
- O resumo recebe apenas os documentos fornecidos, limita fatos/alertas/incertezas e recusa IDs de fonte que não estejam no snapshot. O prompt trata documentos como dados não confiáveis e não habilita ferramentas.
- JEV: `POST https://openrouter.ai/api/v1/systemone`, modelo versionado (`typesafe/jev-1.13` por padrão); não substitui automaticamente por outro modelo. Choice, Noul e Score têm parsers para os campos documentados, com confidence opcional. Para as perguntas Choice da política atual, confidence ausente vira ABSTAIN.
- Política de filtro converte classificação para ALLOW/BLOCK/ABSTAIN em código. Não pede justificativas ou decisões de ordem ao JEV. `apps/api/paperlab/budget.py` implementa reserva e reconciliação transacional, mas ainda não está integrado ao pipeline de chamadas de modelo da aplicação.

### Evidência de validação

**Integração externa não executada.** Testes mocks cobrem formato, schema, referências de fonte, confidence opcional, erros e classificação conservadora. O endpoint manual de validação consulta metadados do modelo sem enviar documentos; o endpoint de resumo/classificação não é acionado pelo worker e nenhum custo foi incorrido por esta entrega.

Referências oficiais conferidas:

- [JEV no OpenRouter](https://openrouter.ai/docs/guides/community/jev)
- [TypeSafe SDK no OpenRouter](https://openrouter.ai/docs/guides/community/typesafe-sdk)
- [Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [Seleção de provedor](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Tipos de resposta e confidence da TypeSafe](https://docs.typesafe.ai/confidence)

## Variáveis

`DATABASE_URL`, `SESSION_SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `COOKIE_SECURE`, `APP_MODE=demo`, `ALPACA_DATA_KEY_ID/SECRET`, credenciais `ALPACA_PAPER_A/B/C_KEY_ID/SECRET`, `OPENROUTER_API_KEY`, `OPENROUTER_LLM_MODEL`, `JEV_MODEL`, `AI_DAILY_BUDGET_USD`, `AI_CALL_BUDGET_USD` e limites `MAX_*` estão listados em `.env.example`. O segredo do administrador e as chaves são somente servidor. Não há variável para habilitar negociação real.
