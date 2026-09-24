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
- O SDK oficial atual documenta `wss://ws.kuru.io/` para o feed de leitura da mainnet, mas não documenta endpoint ativo para Monad Testnet. Por isso, Testnet continua como rede padrão para RPC, porém sem feed Kuru; o sistema deixa `KURU_WS_URL` vazio e bloqueia o botão do monitor. Endereços de contratos de Testnet encontrados em exemplos antigos não são usados como fallback.
- O botão **Iniciar monitor** abre a conexão. Ao parar, o processo fecha o feed e desativa Jev e DRY RUN; uma ordem virtual pendente é cancelada. O serviço fica ocioso depois de iniciar o container. Amostras/eventos/observações de mercado são mantidos por até 30 dias; o ledger simulado permanece separado e é persistido por rede/mercado.
- BUY/SELL no histórico representa apenas o lado agressor de eventos `Trade` publicados pelo feed. Hashes válidos abrem o explorador da rede selecionada. Preços de negócio podem aparecer sem tamanho normalizado, porque a escala de tamanho da Kuru depende do mercado; a aplicação não infere essa escala.
- O DRY RUN vem desligado. Com monitor e Jev ativos, o operador pode ativar o simulador local. Seus filtros usam apenas as escolhas e confidências tipadas do Jev; ordens são fictícias e limitadas a 10 USDC, com confiança mínima de 80%, uma posição comprada por vez e expiração após 120 segundos. Fill estimado ocorre quando uma cotação posterior toca/cruza o limite; fila, taxas e slippage não são modelados, então o P&L é bruto e ilustrativo.

**Validação externa somente leitura em 24/09/2026:** RPC Monad Testnet `https://testnet-rpc.monad.xyz` respondeu com chain ID `0x279f` (10143) e altura de bloco; o host anteriormente configurado `rpc.testnet.monad.xyz` não resolveu por DNS. `ws.testnet.kuru.io` também não resolveu. O endereço de exemplo do SDK Kuru legado `0x05e6f736b5dedd60693fa806ce353156a1b73cf3` e os quatro endereços MONUSDC/DAKMON/CHOGMON/YAKIMON listados no [Kuru Terminal da organização Monad Developers](https://github.com/monad-developers/kuru-terminal) (`0xD3AF145f1Aa1A471b5f0F62c52Cf8fcdc9AB55D3`, `0x94B72620e65577De5FB2b8a8B93328CAf6Ca161b`, `0x277bF4a0AAc16f19d7bf592FeFFc8D2d9a890508`, `0xD5C1Dc181c359f0199c83045A85Cd2556B325De0`) retornaram `eth_getCode = 0x` no RPC atual. Portanto, nenhum desses contratos pode alimentar o monitor e ainda falta um mercado Kuru ativo de Testnet confirmado. Em mainnet, o RPC respondeu com chain ID `0x8f` (143), `eth_getCode` encontrou 141 bytes no contrato `0x065c9d28e428a0db40191a54d33d5b7c71a9c394`, e a assinatura `frontendOrderbook` retornou bid `0.024397` e ask `0.024406`. São valores daquela amostra, não preços fixos. Nenhuma transação foi assinada ou transmitida. OpenRouter não foi chamado por exigir a chave do proprietário.

Referências oficiais: [Monad Developer Portal](https://developers.monad.xyz/) (chain ID 10143), [Monad Network Information - Testnet](https://docs.monad.xyz/developer-essentials/testnet) (reset da Testnet), [Monad JSON-RPC](https://docs.monad.xyz/reference/json-rpc/api), [Kuru Labs Python SDK atual](https://github.com/Kuru-Labs/kuru-sdk-py) (feed read-only atual), [API de mercados Kuru](https://api.kuru.io/api/v1/markets). O endpoint `ws.testnet.kuru.io` e o endereço de exemplo aparecem no [SDK Python legado oficial](https://github.com/Kuru-Labs/kuru-sdk-py-old), mas ambos se mostraram indisponíveis nesta verificação.
