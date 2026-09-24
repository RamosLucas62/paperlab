# Arquitetura

## Componentes

- `apps/web`: Next.js e TypeScript. Interface privada em português; todas as chamadas passam pela rota `/api` do servidor Next. O navegador não recebe tokens de sessão das integrações.
- `apps/api`: FastAPI/Pydantic, regras de aplicação, SQLAlchemy e clientes HTTPX. Sessões administrativas são assinadas, `HttpOnly`, `SameSite=Strict`; ações mutáveis exigem token CSRF. Senhas são armazenadas com Argon2.
- `apps/api/paperlab/worker.py`: processo separado que consulta estado persistido e avança somente experimentos DEMO. Na inicialização ele não coleta dados nem chama modelos ou corretora.
- `apps/api/paperlab/bot_worker.py`: processo separado e controlado pelo banco para o Terminal JEV. Só abre o feed WebSocket Kuru após ação explícita; lê altura de bloco por JSON-RPC Monad. Jev roda sob ativação, reserva de orçamento e intervalo configurado. `simulation.py` converte classificações tipadas e filtradas em ledger virtual opcional; não importa cliente de carteira/RPC de escrita e não assina nem envia transações.
- `apps/api/paperlab/market_feed.py`: normaliza snapshots do livro e negócios reportados pela Kuru sem inferir preço/tamanho ausentes. `MarketSample`, `MarketEvent` e `JevObservation` guardam dados do mercado; tabelas próprias guardam decisões, ordens, fills e conta DRY RUN, isoladas das tabelas DEMO/PAPER.
- `apps/api/migrations`: migração Alembic inicial. SQLite é usado para desenvolvimento offline; PostgreSQL é o destino recomendado para coordenação persistente e pode ser local ou uma instância Supabase dedicada.
- `packages/policy/filter-v1.json`: parâmetros versionados de classificação. `fixtures/demo_news.json`: notícias inventadas para exercício da interface, sempre sintéticas.

## Persistência e rastreabilidade

Experimentos guardam modo, configuração congelada e hash. Snapshots guardam payload, cutoff, origem, versão e hash. Barras, versões de notícias, decisões, chamadas de modelo, intenções, fills, retratos de carteira, eventos das integrações e reservas de orçamento relacionam-se por identificadores e restrições de unicidade. O terminal tem armazenamento próprio para amostras Kuru, eventos negociados e classificações Jev. Valores de mercado usam `NUMERIC` e `Decimal`; timestamps persistidos usam UTC. A interface formata horários em `America/Sao_Paulo` e mostra o fuso.

Na DEMO, o gerador usa seed fixa e valores artificiais. A estratégia cria o candidato SMA 20/50 a partir de barras fechadas; cada braço aplica sua decisão de filtro e seu próprio saldo sintético. Saídas seguem o mesmo ramo determinístico e não dependem da classificação textual. Fees DEMO são uma hipótese ilustrativa versionada, não uma tarifa da Alpaca.

## Limites de execução atuais

O modo de experimento continua fixado em DEMO; a interface não cria experimentos PAPER ou REPLAY. A Kuru/Monad seguem somente leitura. O DRY RUN opcional calcula P&L bruto com regras e hipóteses locais visíveis na tela; Jev não chama exchange. Não há carteira nem caminho de execução de ordem Monad/Kuru. As integrações Alpaca permanecem sem ligação ao worker. Reservas de orçamento protegem chamadas Jev iniciadas explicitamente no terminal.

## Fronteiras de segurança

- O host de ordens é uma constante exata HTTPS; redirecionamentos são bloqueados, TLS permanece ativo e variáveis de proxy do processo são ignoradas pelo cliente.
- O cliente de mercado/notícias é outro adaptador de somente leitura.
- Chaves ficam em variáveis de ambiente e não são gravadas em entidades persistentes ou enviadas ao browser.
- O modo PAPER, quando implementado como fluxo completo, deve exigir três `account_id` distintos, nenhuma posição/ordem herdada e pré-condições equivalentes antes de criar bindings A/B/C. A função de preflight já verifica estes estados em leitura; não muda nem limpa contas.
- DEMO, PAPER e REPLAY não devem compartilhar relatórios. Atualmente só DEMO possui painel funcional.
