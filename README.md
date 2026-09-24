# PaperLab

Piloto privado de cinco dias para observar decisões do Jev sobre o mercado MON/USDC da Kuru e uma carteira virtual inicial de 1.000 USDC. A meta de chegar a 10.000 USDC em 90 dias é uma referência para avaliar, não uma projeção. Cinco dias não demonstram que esse resultado se repetiria por três meses.

## Estado desta entrega

- A tela principal agora é o **piloto de cinco dias**. Um botão liga o feed Kuru, as classificações Jev e o simulador DRY RUN. O relógio começa na primeira cotação válida; pausar não reinicia o prazo. No primeiro dado recebido após o quinto dia, o saldo virtual é congelado e as chamadas Jev param.
- A DEMO sintética A/B/C continua preservada no banco e nas APIs antigas, mas saiu da navegação principal para não ser confundida com os dados reais do piloto.
- **Sem execução real:** o DRY RUN registra ordens, fills, posição e P&L bruto fictícios. A regra local exige confiança mínima de 80%, usa ordens de 10 USDC e só considera fill quando uma cotação oposta posterior toca/cruza o limite. A simulação não conhece fila, impacto, taxas nem slippage; os resultados não representam execução ou rentabilidade reais. Não há carteira, assinatura, transmissão de transação ou variável para liberar negociação real.
- BUY/SELL na fita identifica o lado agressor do mercado Kuru e nunca aciona ordens. Somente classificações Jev válidas, com relevância, risco e suficiência aprovados por filtros determinísticos, podem alimentar o DRY RUN. A DEMO antiga continua independente do feed Kuru.
- **Integração externa precisa ser configurada na VPS:** um endereço MON/USDC verificado para leitura em mainnet está documentado em [EasyPanel](docs/easypanel.md). O RPC Testnet funciona, mas a Kuru não documenta feed WSS ativo nessa rede; o monitor permanece bloqueado até haver feed e mercado válidos. OpenRouter é opcional; chamadas Jev podem ter custo e respeitam os limites de orçamento configurados.
- O piloto mede comportamento e resultado virtual observado, mas suas ordens de 10 USDC e seu modelo de execução incompleto não permitem concluir que o capital total de 1.000 USDC poderia crescer 10 vezes. Ver [limitações](docs/limitations.md).

## Requisitos

- Python 3.12, Node.js 22 e npm.
- Docker Compose opcional para PostgreSQL local.
- Uma instalação offline não requer chaves da Alpaca nem do OpenRouter.

## Subir DEMO local

Na raiz do projeto:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm --prefix apps/web ci
cp .env.example .env
```

Edite `.env`: crie um `SESSION_SECRET_KEY` aleatório com pelo menos 32 caracteres e defina uma senha de administrador exclusiva com pelo menos 12 caracteres. Esses valores são locais e não devem ser commitados. Depois execute em três terminais, todos na raiz do repositório:

```sh
set -a; source .env; set +a
PYTHONPATH=apps/api .venv/bin/uvicorn paperlab.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

```sh
set -a; source .env; set +a
PYTHONPATH=apps/api .venv/bin/python -m paperlab.worker
```

```sh
npm --prefix apps/web run dev
```

Abra http://127.0.0.1:3000 e entre com o administrador definido no `.env`. A primeira execução cria o banco SQLite local e uma experiência pausada com histórico sintético. O worker avança uma barra sintética por intervalo configurado; o botão de iniciar também grava o primeiro ciclo. Não use esses dados para avaliação de mercado.

## PostgreSQL local com Compose

Configure `.env` como acima. O Compose publica somente em `127.0.0.1`; a senha do banco do Compose é local de desenvolvimento. Rode a migração antes de iniciar os serviços:

```sh
docker compose up -d postgres
docker compose --profile tools run --rm migrate
docker compose up --build api worker web
```

Abra http://127.0.0.1:3000. Para encerrar os serviços, use `docker compose down`; para apagar o banco local e seus dados de demonstração, use `docker compose down -v`.

## Publicar o código e hospedar na VPS com EasyPanel

O Compose de produção para o painel está em `docker-compose.easypanel.yml`. Ele publica só o serviço web pelo proxy do EasyPanel; API e PostgreSQL permanecem na rede privada do Compose. A aplicação ainda exige login administrativo mesmo com repositório público.

1. Use o repositório público [RamosLucas62/paperlab](https://github.com/RamosLucas62/paperlab), já sincronizado com a branch `main`. Não adicione `.env`, banco local, chaves, certificados, `.venv` ou `node_modules`. O `.gitignore` e `.dockerignore` filtram esses arquivos.
2. No EasyPanel, crie um serviço **Compose** com fonte **GitHub** (`owner/paperlab`), branch `main`, build path `/` e arquivo `docker-compose.easypanel.yml`. Repositórios públicos não precisam de token GitHub segundo o [guia de fontes do EasyPanel](https://easypanel.io/docs/services/app).
3. Em Environment, configure `POSTGRES_PASSWORD` como segredo aleatório de 32 bytes hexadecimais, `SESSION_SECRET_KEY` como segredo aleatório com pelo menos 32 caracteres, `ADMIN_USERNAME` e uma `ADMIN_PASSWORD` exclusiva com pelo menos 12 caracteres. Senhas hexadecimais evitam caracteres que precisariam de escape na URL PostgreSQL.
4. Faça Deploy. A API espera o Postgres saudável e aplica Alembic ao banco local da VPS antes de iniciar. O volume `paperlab-postgres` mantém os dados entre recriações; configure e teste backups no provedor/VPS antes de atualizações relevantes.
5. Em Domains, direcione o domínio ao serviço `web`, porta `3000`, habilite certificado HTTPS e redirecionamento HTTP→HTTPS. Aponte o registro DNS `A` do domínio para o IP da VPS e libere 80/443 no firewall. Não crie domínio ou porta pública para `api` ou `postgres`.
6. Depois de verificar o domínio e o certificado, entre com as credenciais administrativas configuradas. O piloto aparece como tela principal; configure mercado, feed e OpenRouter antes de clicar em **Iniciar piloto de 5 dias**. As portas não são publicadas pelo Compose para o host.

O Compose local `docker-compose.yml` continua usando ligações em `127.0.0.1`; use o arquivo EasyPanel acima na VPS. O guia completo e as verificações de produção estão em [docs/easypanel.md](docs/easypanel.md). O EasyPanel oferece domínio/HTTPS e deploy de Compose a partir de GitHub na própria interface; consulte a [documentação de Compose](https://easypanel.io/docs/services/compose) e [domínios](https://easypanel.io/docs/services/compose#domains) para os campos atuais.

**Atualização da VPS:** após publicar esta alteração na branch `main`, sincronize e reimplante o Compose existente para aplicar a migração `0005_five_day_pilot`. O banco e o piloto DRY RUN anterior são preservados; se ele já tiver começado, seu horário original passa a ser o início do prazo de cinco dias. Veja [docs/easypanel.md](docs/easypanel.md). Nenhum segredo deve ser enviado pelo chat ou commitado no repositório.

## Testes e checagens locais

```sh
.venv/bin/pytest
npm --prefix apps/web run build
```

O teste de navegador exige Chromium instalado pelo Playwright, as dependências Python acima e `.env` carregado no ambiente:

```sh
npm --prefix apps/web exec playwright install chromium
set -a; source .env; set +a
PATH="$PWD/.venv/bin:$PATH" npm --prefix apps/web run test:e2e
```

As chamadas externas não são executadas por instalação, build ou testes padrão. Nenhum teste PAPER com credenciais foi executado nesta entrega.

## Migrações

Com `.env` carregado e `DATABASE_URL` apontando para um banco local dedicado:

```sh
set -a; source .env; set +a
PYTHONPATH=apps/api .venv/bin/alembic -c apps/api/alembic.ini upgrade head
PYTHONPATH=apps/api .venv/bin/alembic -c apps/api/alembic.ini check
```

Isso não deve ser apontado a um banco Supabase ou outro banco externo durante desenvolvimento. A configuração aceita `DATABASE_URL` PostgreSQL dedicado, mas migrações externas devem ser avaliadas e autorizadas pelo responsável do ambiente.

## Integrações e variáveis

Veja [.env.example](.env.example) e [integrações](docs/integrations.md). Para diagnósticos autenticados, cadastre credenciais paper separadas em A, B e C, credencial Alpaca para dados e chave OpenRouter no ambiente privado da aplicação. Não envie segredos no chat, frontend, fixtures ou commits. Os botões de diagnóstico não enviam ordens.

O piloto não conecta uma corretora. O simulador mantém um livro virtual separado da DEMO e do feed público; não envia ordens Monad/Kuru.

## Documentação

- [Arquitetura](docs/architecture.md)
- [Integrações e referências verificadas](docs/integrations.md)
- [Experimentos e interpretação](docs/experiment.md)
- [Limitações e pendências](docs/limitations.md)
