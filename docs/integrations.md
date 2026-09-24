# Integrações e validação

Documentação oficial consultada em 24/09/2026. Os adaptadores têm testes offline com `httpx.MockTransport`; isso verifica validação de requisições e respostas simuladas, não acesso de conta real.

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

**Alpaca externa não executada.** Não havia credenciais autorizadas disponíveis nesta entrega. Nenhuma conta foi acessada e nenhuma ordem paper foi enviada. Cobertura mock inclui host não paper, redirect, timeout/consulta por ID, deduplicação de candles, corte de barra aberta, mapeamento/ausência de notícias, status desconhecido e preflight de IDs/saldos.

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
- JEV: `POST https://openrouter.ai/api/alpha/decisions`, modelo versionado (`typesafe/jev-1.13` por padrão); não substitui automaticamente por outro modelo. O corpo envia o objeto `state` e perguntas tipadas. Choice, Noul e Score têm parsers para os campos documentados, com confidence opcional.
- No Terminal JEV, o modelo recebe somente amostras de preço/spread da Kuru e classifica uma postura de sombra (`BUY`/`SELL`/`HOLD`), relevância, risco aparente e suficiência dos dados. O rótulo é observacional; não é recomendação e não aciona ordens. A chamada exige ativação no terminal, tem intervalo mínimo e reserva o teto por chamada antes de consultar. Se o provedor não reportar custo, a reserva permanece como custo desconhecido.

### Evidência de validação

**OpenRouter/JEV externo não executado nesta sessão.** Testes mocks cobrem formato de resumo, endpoint alpha do JEV, estado tipado, confidence opcional e erros. Nenhuma chamada faturável foi feita nesta sessão.

Referências oficiais conferidas:

- [JEV no OpenRouter](https://openrouter.ai/blog/tutorials/how-to-use-jev/)
- [TypeSafe SDK no OpenRouter](https://openrouter.ai/docs/guides/community/typesafe-sdk)
- [Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [Seleção de provedor](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Tipos de resposta e confidence da TypeSafe](https://docs.typesafe.ai/confidence)

## Variáveis

`DATABASE_URL`, `SESSION_SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `COOKIE_SECURE`, `APP_MODE=demo`, credenciais Alpaca, `OPENROUTER_API_KEY`, `OPENROUTER_LLM_MODEL`, `JEV_MODEL`, limites de orçamento, `MONAD_RPC_URL`, `MONAD_CHAIN_ID`, `KURU_WS_URL`, `KURU_MARKET_ADDRESS`, `KURU_SYMBOL`, `TERMINAL_SAMPLE_INTERVAL_SECONDS` e `TERMINAL_JEV_INTERVAL_SECONDS` estão listados em `.env.example`. O segredo do administrador, chaves e endereço do mercado são configurações de servidor; nenhuma chave de carteira é usada. Não há variável para habilitar negociação real.

## Monad e Kuru

- O terminal usa `eth_chainId` e `eth_blockNumber` por JSON-RPC. Aceita Monad Testnet (10143, padrão) ou Monad Mainnet (143, observação somente leitura), e confere o RPC ao iniciar o monitor.
- O serviço separado `bot` assina `frontendOrderbook` no WebSocket Kuru (`KURU_WS_URL`) para `KURU_MARKET_ADDRESS`. O host precisa corresponder ao chain ID. Antes da conexão, `eth_getCode` confirma bytecode do mercado na mesma rede. O serviço não recebe carteira nem chave privada, não assina e não envia transações.
- O botão **Iniciar monitor** abre a conexão. Ao parar, o processo fecha o feed e desativa Jev. O serviço fica ocioso depois de iniciar o container. O terminal mantém no máximo 30 dias de amostras/eventos/observações.
- BUY/SELL no histórico representa apenas o lado agressor de eventos `Trade` publicados pelo feed. Hashes válidos abrem o explorador da rede selecionada. Preços de negócio podem aparecer sem tamanho normalizado, porque a escala de tamanho da Kuru depende do mercado; a aplicação não infere essa escala.

**Validação externa somente leitura em 24/09/2026:** RPC Monad Mainnet respondeu com chain ID `0x8f` (143), `eth_getCode` encontrou 141 bytes no contrato `0x065c9d28e428a0db40191a54d33d5b7c71a9c394`, e a assinatura `frontendOrderbook` retornou bid `0.024397` e ask `0.024406`. São valores daquela amostra, não preços fixos. `ws.testnet.kuru.io` e o RPC público de testnet não resolveram por DNS neste ambiente; não há endereço Kuru MON/USDC de testnet validado aqui. Nenhuma transação foi assinada ou transmitida. OpenRouter não foi chamado por exigir a chave do proprietário.

Referências oficiais: [Monad Developer Hub](https://monad.xyz/developers) (RPCs, chain IDs e explorers), [Monad JSON-RPC](https://docs.monad.xyz/reference/json-rpc/api), [Kuru Labs Python SDK](https://github.com/Kuru-Labs/kuru-sdk-py) (feed read-only atual), [API de mercados Kuru](https://api.kuru.io/api/v1/markets). O endpoint `ws.testnet.kuru.io` aparece no [SDK Python legado oficial](https://github.com/Kuru-Labs/kuru-sdk-py-old), mas sua disponibilidade não foi confirmada.
