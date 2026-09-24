# Publicação no GitHub e deploy em EasyPanel

## Modelo de exposição

O repositório de código é público; isso não torna o painel anônimo. O aplicativo mantém sua tela de login administrativo. Na VPS, o proxy do EasyPanel fornece o domínio público/HTTPS somente ao container `web`; o container `api` e o banco Postgres não recebem uma rota pública ou porta publicada. O frontend conversa com API pela rede privada do Compose.

EasyPanel documenta suporte a um Compose associado ao GitHub, domínio ligado a serviço+porta e deploy com Docker Compose. Neste projeto, o build path é a raiz por causa dos Dockerfiles, fixtures, policy e requirements compartilhados. Veja a [documentação de Compose](https://easypanel.io/docs/services/compose), [App/GitHub source](https://easypanel.io/docs/services/app) e [configuração de domínios](https://easypanel.io/docs/services/compose#domains).

## Arquivo e serviços

Use `docker-compose.easypanel.yml`, com build path `/`. A configuração não declara `ports`, portanto o proxy EasyPanel é o único ponto de entrada. O domínio deve apontar para `web:3000`. Não associe domínios a `api` ou `postgres`.

Os serviços são:

- `postgres`: imagem fixada na série PostgreSQL 16, volume nomeado persistente, senha fornecida por variável do EasyPanel e health check.
- `api`: imagem do backend, aguarda Postgres, executa `alembic upgrade head` contra o banco privado do próprio serviço e inicia FastAPI. Cookie seguro habilitado para HTTPS.
- `worker`: processo Python separado em DEMO, com o mesmo banco privado. Não realiza requisições externas automaticamente.
- `bot`: worker de leitura Kuru/Monad e DRY RUN local para o Terminal JEV. Fica ocioso até o operador ativar o monitor; Jev e simulador têm ativações separadas.
- `web`: Next.js atrás do proxy, com URL interna `http://api:8000` incorporada no build para as rewrites de produção.

O proxy `web` exige porta 3000. Habilite o certificado TLS e, após testar, redirecionamento de HTTP para HTTPS no EasyPanel. O DNS precisa apontar ao VPS; mantenha 80/443 liberadas no firewall. A [instalação oficial do EasyPanel](https://easypanel.io/docs) recomenda VPS Ubuntu nova, ao menos 2 GB de RAM e portas 80/443 disponíveis.

## Variáveis no EasyPanel

Cadastre no editor de ambiente do Compose:

| Nome | Valor |
|---|---|
| `POSTGRES_PASSWORD` | Segredo de 32 bytes hexadecimais, sem espaços. A URL PostgreSQL é interpolada pelo compose. |
| `SESSION_SECRET_KEY` | Segredo aleatório de pelo menos 32 caracteres. |
| `ADMIN_USERNAME` | Usuário administrativo escolhido pelo proprietário. |
| `ADMIN_PASSWORD` | Senha exclusiva com ao menos 12 caracteres. |
| `WORKER_INTERVAL_SECONDS` | Opcional; padrão 60. |
| `MONAD_RPC_URL` | Opcional; vazio seleciona o RPC público conforme `MONAD_CHAIN_ID`. Consulta somente chain ID, bloco e bytecode do mercado. |
| `MONAD_CHAIN_ID` | `10143` (Monad Testnet, padrão) ou `143` (Monad Mainnet em modo somente leitura). Outros IDs são recusados. |
| `KURU_WS_URL` | Opcional; vazio seleciona `wss://ws.kuru.io` somente na mainnet. O SDK atual não documenta um feed WSS ativo para a Testnet; não use o host legado `ws.testnet.kuru.io`. |
| `KURU_MARKET_ADDRESS` | Endereço do mercado MON/USDC Kuru na rede selecionada. Na mainnet somente leitura, o endereço conferido é `0x065c9d28e428a0db40191a54d33d5b7c71a9c394`. Na testnet, um contrato sem feed WSS ativo não habilita o monitor. |
| `KURU_SYMBOL` | Opcional; padrão `MON/USDC`, rótulo mostrado no painel. |
| `TERMINAL_SAMPLE_INTERVAL_SECONDS` | Opcional; intervalo mínimo de gravação das amostras do gráfico; padrão 5 segundos. |
| `OPENROUTER_API_KEY` | Opcional; necessário apenas para ativar Jev. A chave não deve ser enviada no chat ou navegador. |
| `JEV_MODEL` | Opcional; padrão `typesafe/jev-1.13`. Use uma versão fixa. |
| `AI_CALL_BUDGET_USD` / `AI_DAILY_BUDGET_USD` | Limites reservados antes das chamadas Jev; padrões US$ 0,10 e US$ 2,00. |
| `TERMINAL_JEV_INTERVAL_SECONDS` | Opcional; intervalo mínimo entre classificações; padrão 120 segundos. |

Não cadastre credenciais Alpaca ou OpenRouter para servir a DEMO. Não inclua segredos no GitHub, build args, logs ou frontend. Alterações de variável exigem redeploy. Como a URL do banco incorpora `POSTGRES_PASSWORD`, use hex sem pontuação para evitar necessidade de percent-encoding.

## Procedimento de deploy

1. Use o repositório público [RamosLucas62/paperlab](https://github.com/RamosLucas62/paperlab), branch `main`.
2. Ao atualizar o projeto, inspecione os arquivos staged e confirme que `.env`, bancos SQLite, `.venv`, `node_modules` e builds locais não foram incluídos.
3. No EasyPanel: New Service → Compose → GitHub; informe `owner/paperlab`, branch `main`, Build Path `/`, arquivo `docker-compose.easypanel.yml`.
4. Configure as quatro variáveis obrigatórias acima. Use senhas diferentes para admin, Postgres e assinatura de sessão.
5. Faça Deploy e verifique a saúde de `postgres`, `api`, `worker`, `bot` e `web`. A primeira inicialização cria/atualiza o schema do banco privado da VPS antes de subir a API.
6. Associe um hostname ao serviço `web` na porta interna `3000`, em HTTPS. Não publique a porta 8000 ou 5432.
7. Confirme o login e o Terminal JEV. Para usar o feed, configure `KURU_MARKET_ADDRESS` na rede selecionada e reinicie `api` e `bot`; depois ative, nessa ordem, o monitor, o Jev e o **DRY RUN**. A migração `0004_terminal_dry_run` é aplicada pela API. O DRY RUN mantém ordens e posição fictícias no banco; nenhuma ordem ou transação é enviada à Kuru/Monad.
8. Configure backup externo testável do volume Postgres. Um volume Docker sozinho não é backup.

## Atualizar a instalação existente

Para a VPS PaperLab já configurada no EasyPanel, mantenha o serviço Compose atual ligado ao repositório e à branch `main`; sincronize e faça Deploy após o push. A migração `0004_terminal_dry_run` é aplicada pela inicialização da API, preservando o volume Postgres e todo o histórico existente. O serviço `bot` sobe parado, sem conexão externa, até **Iniciar monitor**. Cadastre `KURU_MARKET_ADDRESS` no Environment do Compose antes de iniciar o feed. A chave OpenRouter é opcional e só deve ser inserida se o Jev for ativado. Depois do deploy, ligue o monitor, o Jev e, por último, o DRY RUN na tela. Não é preciso recriar o domínio nem adicionar variáveis para o simulador. Ao mudar o chain ID, a aplicação pausa monitor, Jev e simulação, cancela ordens simuladas pendentes e separa o histórico por rede.

### Observação de mercado atual

A configuração padrão continua na Monad Testnet, mas o monitor fica bloqueado: o RPC responde com chain ID `10143`, enquanto a Kuru não documenta um feed WSS ativo de Testnet no SDK atual. O host `ws.testnet.kuru.io` não resolve e cinco endereços de mercado de referências antigas (incluindo o exemplo do SDK legado e quatro do [Kuru Terminal da organização Monad Developers](https://github.com/monad-developers/kuru-terminal)) retornam `eth_getCode = 0x` no RPC atual. Não preencha esses hosts ou endereços antigos. Para observar o mercado público MON/USDC da mainnet sem enviar transações, selecione explicitamente a rede e use estas variáveis no Environment do Compose:

```env
MONAD_CHAIN_ID=143
MONAD_RPC_URL=https://rpc.monad.xyz
KURU_WS_URL=wss://ws.kuru.io/
KURU_MARKET_ADDRESS=0x065c9d28e428a0db40191a54d33d5b7c71a9c394
KURU_SYMBOL=MON/USDC
```

Isso só lê dados públicos: o PaperLab não recebe carteira ou chave privada e o serviço não assina nem transmite ordens Kuru. Se preferir ficar na Testnet, mantenha `MONAD_CHAIN_ID=10143` e `KURU_WS_URL` vazio; o monitor permanecerá desativado até que a Kuru publique um feed WSS ativo e exista um contrato de mercado nessa rede.

## GitHub público e licença

A listagem do código está pública no GitHub. Não foi adicionada licença de código, pois isso define direitos de reutilização; a ausência de um arquivo de licença não concede uma licença permissiva.
