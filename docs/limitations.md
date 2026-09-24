# Limitações e pendências conhecidas

Esta entrega contém uma DEMO funcional e componentes isolados de integração; não é um executor conectado nem um sistema para decisão financeira.

## Ainda não implementado no fluxo da aplicação

1. Criação/execução de experimentos PAPER A/B/C, vinculação persistente das três contas após preflight e aplicação da mesma configuração em contas isoladas.
2. Coleta central de bars/news PAPER com snapshots imutáveis, política de cutoff, detecção de lacunas degradadas e armazenamento de versões de notícia.
3. Orquestração de análise real B/C ligada a reservas de orçamento antes da chamada, custo desconhecido reconciliável, cache e controle de concorrência.
4. Worker operacional PAPER que persiste intenção, revalida controles/dado recente, envia/cancela, ingere eventos/fills idempotentes e retoma reconciliação após reinício. Há métodos do cliente HTTP isolado; eles não equivalem a esse fluxo.
5. REPLAY usando apenas respostas/snapshots gravados e livro próprio com hipóteses de execução explícitas.
6. Métricas comparativas PAPER, custo real atribuível a IA/infraestrutura, performance no intervalo comum e estado de degradação no dashboard.
7. Testes autenticados opt-in para as integrações externas e testes de integração PostgreSQL multi-worker. Nenhum deles foi executado.

## Riscos de interpretação

- Valores, eventos, labels de classificação, fills e fee rate da DEMO são sintéticos. Não medem latência, spread, liquidez, slippage ou desempenho da Alpaca.
- Paper trading da corretora também é uma simulação e não reproduz todo o comportamento de uma execução real. Nenhum resultado deste laboratório demonstra que uma regra está apta para dinheiro real.
- O período de avaliação futura deve ser prospectivo. Replay de saídas de modelo produzidas hoje pode conter informação futura em relação às barras antigas.
- Um teto de perda simulado não garante a perda máxima; gaps, execução, falhas externas e comportamento da plataforma podem divergir.
- A estratégia SMA 20/50 e os thresholds da política são presets didáticos, não calibrados nem recomendações.
- O teste E2E cobre apenas o caminho DEMO local e determinístico.
