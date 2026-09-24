# PaperLab

Laboratório privado para comparar três versões de uma regra didática: A usa apenas cruzamento SMA 20/50; B acrescenta JEV; C acrescenta resumo generativo e JEV. O produto começa pausado em **DEMO** e os dados sintéticos são identificados permanentemente. Ele não avalia rentabilidade nem implementa negociação real.

## Estado desta entrega

- A DEMO sintética continua disponível no painel: login, experimentos, ciclos, diferenças A/B/C rastreáveis e exportação JSON/CSV.
- O **Terminal JEV** acrescenta feed do livro/negociações Kuru e altura da Monad em modo somente leitura, mais classificações Jev opcionais em modo sombra. O monitor só inicia após ação no painel; Jev permanece desligado até ativação explícita.
- **Sem execução de ordens:** esta etapa não conecta carteira, não assina nem envia transações e não calcula P&L. BUY/SELL na fita identifica o lado agressor informado pela Kuru, não ordens do PaperLab. BUY/SELL/HOLD do Jev é somente uma postura observacional de sombra. A DEMO antiga não usa dados da Kuru.
- **Integração externa ainda precisa ser configurada na VPS:** não foi fornecido endereço de mercado Kuru nem chave OpenRouter. As chamadas Jev podem ter custo e respeitam os limites de orçamento configurados.
- REPLAY, pipeline PAPER ponta a ponta, reconciliação contínua de eventos/fills e avaliação por dados prospectivos permanecem fora do fluxo funcional atual. Ver [limitações](docs/limitations.md).

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
6. Depois de verificar o domínio e o certificado, entre com as credenciais administrativas configuradas. O Terminal JEV aparece como tela principal; configure o mercado antes de iniciar o monitor. As portas não são publicadas pelo Compose para o host.

O Compose local `docker-compose.yml` continua usando ligações em `127.0.0.1`; use o arquivo EasyPanel acima na VPS. O guia completo e as verificações de produção estão em [docs/easypanel.md](docs/easypanel.md). O EasyPanel oferece domínio/HTTPS e deploy de Compose a partir de GitHub na própria interface; consulte a [documentação de Compose](https://easypanel.io/docs/services/compose) e [domínios](https://easypanel.io/docs/services/compose#domains) para os campos atuais.

**Atualização da VPS:** a implementação está publicada na branch `main`. No EasyPanel já configurado, sincronize e reimplante o Compose existente para aplicar a migração e iniciar o serviço `bot` em espera. O feed de mercado só começa depois de configurar `KURU_MARKET_ADDRESS` e clicar em **Iniciar monitor**. Veja [docs/easypanel.md](docs/easypanel.md). Nenhum segredo deve ser enviado pelo chat ou commitado no repositório.

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

O Terminal JEV não é um fluxo PAPER nem conecta uma corretora. Ele mantém feed e classificações observacionais isolados da DEMO e não contém fluxo de envio de ordens Monad/Kuru.

## Documentação

- [Arquitetura](docs/architecture.md)
- [Integrações e referências verificadas](docs/integrations.md)
- [Experimentos e interpretação](docs/experiment.md)
- [Limitações e pendências](docs/limitations.md)
