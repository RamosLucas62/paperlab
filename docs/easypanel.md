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

Não cadastre credenciais Alpaca ou OpenRouter para servir a DEMO. Não inclua segredos no GitHub, build args, logs ou frontend. Alterações de variável exigem redeploy. Como a URL do banco incorpora `POSTGRES_PASSWORD`, use hex sem pontuação para evitar necessidade de percent-encoding.

## Procedimento de deploy

1. Use o repositório público [RamosLucas62/paperlab](https://github.com/RamosLucas62/paperlab), cuja branch `main` contém o projeto. O commit `ca25b5b` também corrigiu o lock de dependências para Python 3.12.
2. Ao atualizar o projeto, inspecione os arquivos staged e confirme que `.env`, bancos SQLite, `.venv`, `node_modules` e builds locais não foram incluídos.
3. No EasyPanel: New Service → Compose → GitHub; informe `owner/paperlab`, branch `main`, Build Path `/`, arquivo `docker-compose.easypanel.yml`.
4. Configure as quatro variáveis obrigatórias acima. Use senhas diferentes para admin, Postgres e assinatura de sessão.
5. Faça Deploy e verifique a saúde de `postgres`, `api`, `worker` e `web`. A primeira inicialização cria/atualiza o schema do banco privado da VPS antes de subir a API.
6. Associe um hostname ao serviço `web` na porta interna `3000`, em HTTPS. Não publique a porta 8000 ou 5432.
7. Confirme o login e o banner sintético DEMO, exporte um ciclo e verifique os logs. O produto ainda não executa PAPER ou REPLAY.
8. Configure backup externo testável do volume Postgres. Um volume Docker sozinho não é backup.

## Estado do deploy

O workflow do GitHub para o commit `ca25b5b` concluiu com sucesso nos jobs de Python e web: [ver execução](https://github.com/RamosLucas62/paperlab/actions/runs/36002792228). O deploy na VPS ainda não foi executado: não foi informado um domínio apontado para a VPS nem foi conectado um serviço EasyPanel nesta sessão. Para concluir, crie o serviço Compose seguindo o procedimento acima, cadastre os segredos diretamente no EasyPanel e associe o domínio da VPS ao serviço `web`. Não envie senhas ou chaves pelo chat.

## GitHub público e licença

A listagem do código está pública no GitHub. Não foi adicionada licença de código, pois isso define direitos de reutilização; a ausência de um arquivo de licença não concede uma licença permissiva.
