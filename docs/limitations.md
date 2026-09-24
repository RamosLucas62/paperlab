# Limitações e pendências conhecidas

Esta entrega contém uma DEMO funcional, um terminal conectado a fontes externas somente leitura e um simulador local opt-in. O simulador não é um executor nem um sistema para decisão financeira.

## Ainda não implementado no fluxo da aplicação

1. Criação/execução de experimentos PAPER A/B/C, vinculação persistente das três contas após preflight e aplicação da mesma configuração em contas isoladas.
2. Coleta central de bars/news PAPER com snapshots imutáveis, política de cutoff, detecção de lacunas degradadas e armazenamento de versões de notícia.
3. Orquestração de análise real B/C ligada a reservas de orçamento antes da chamada, custo desconhecido reconciliável, cache e controle de concorrência.
4. Worker operacional PAPER que persiste intenção, revalida controles/dado recente, envia/cancela, ingere eventos/fills idempotentes e retoma reconciliação após reinício. Há métodos do cliente HTTP isolado; eles não equivalem a esse fluxo.
5. REPLAY usando apenas respostas/snapshots gravados e livro próprio com hipóteses de execução explícitas.
6. Métricas comparativas PAPER, custo real atribuível a IA/infraestrutura, performance no intervalo comum e estado de degradação no dashboard.
7. Testes autenticados opt-in para as integrações externas e testes de integração PostgreSQL multi-worker. Nenhum deles foi executado.

## Limitações do DRY RUN Monad/Kuru

- A conta é fictícia: começa com 1.000 USDC virtuais, limita cada ordem a 10 USDC, exige confiança mínima de 80%, permite só uma posição comprada e bloqueia vendas descobertas. Cada ordem limite expira após 120 segundos.
- O preenchimento é uma hipótese local: considera fill integral quando uma cotação oposta posterior toca ou cruza o limite. Não modela fila, liquidez executável, impacto de mercado, latência de execução, taxas, gas nem slippage. Portanto, o P&L mostrado é bruto e pode diferir muito de qualquer execução real.
- O simulador só considera resultados Jev tipados com postura BUY/SELL/HOLD, relevância, ausência de risco e suficiência dos dados; cada campo precisa superar 80%. HOLD, falhas, limites de custo, dados fracos, exposição existente e posição ausente para venda não geram uma nova ordem.
- O worker persiste ledger separado por rede e mercado. Trocar rede, parar o monitor ou desativar Jev/DRY RUN cancela ordens pendentes, sem apagar posição ou histórico virtual.
- O feed público e o livro podem estar incompletos, atrasados ou indisponíveis. Uma cotação tocada não prova que uma ordem seria preenchida no mercado.

## Riscos de interpretação

- Valores, eventos, labels de classificação, fills e fee rate da DEMO são sintéticos. Não medem latência, spread, liquidez, slippage ou desempenho da Alpaca.
- Paper trading da corretora também é uma simulação e não reproduz todo o comportamento de uma execução real. Nenhum resultado deste laboratório demonstra que uma regra está apta para dinheiro real.
- O período de avaliação futura deve ser prospectivo. Replay de saídas de modelo produzidas hoje pode conter informação futura em relação às barras antigas.
- Um teto de perda simulado não garante a perda máxima; gaps, execução, falhas externas e comportamento da plataforma podem divergir.
- A estratégia SMA 20/50 e os thresholds da política são presets didáticos, não calibrados nem recomendações.
- Os E2E cobrem DEMO local e estados simulados do Terminal; não validam feed externo, OpenRouter, PostgreSQL multi-worker ou execução real.
- O feed real só funciona depois de informar um endereço de mercado Kuru correto. O tamanho de negócios não é mostrado quando sua unidade depende de uma precisão ainda não configurada.
- Classificações Jev dependem de serviço externo faturável, podem falhar ou não reportar custo. Elas descrevem os campos enviados e não validam uma estratégia.
