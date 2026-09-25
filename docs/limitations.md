# Limitações e pendências conhecidas

Esta entrega mostra um piloto de cinco dias com feed externo somente leitura e simulador local. A DEMO antiga permanece no banco, mas não aparece na navegação principal. O simulador não é um executor nem um sistema para decisão financeira.

## Novo piloto baseado no livro da Kuru

- O teste novo preserva o livro virtual anterior em tabelas separadas. Compara duas contas virtuais de 1.000 USDC: uma regra determinística baseada no topo do livro e no movimento de 30 segundos, e a mesma oportunidade filtrada pelo Jev. O Jev pode escolher BUY, SELL ou HOLD. A comparação mede o valor incremental do filtro de IA, não uma estratégia de mercado independente.
- O feed é amostrado aproximadamente a cada segundo e avaliado a cada cinco segundos quando recebe mensagens. O Jev só é consultado se a regra encontra uma oportunidade ou se sua carteira já tem posição. Orçamento, latência, feed ausente e dados fracos podem reduzir muito o número de chamadas. Esta cadência não é negociação a cada bloco nem HFT.
- As duas contas podem usar até o saldo virtual disponível em uma posição comprada de MON; não há venda descoberta, alavancagem ou carteira real. Ordens limites virtuais expiram em 15 segundos e são consideradas integralmente preenchidas quando uma cotação oposta posterior toca o preço. Não há medição de posição na fila, profundidade disponível para 1.000 USDC, liquidez do livro inteiro, execução parcial ou impacto de mercado.
- O resultado deduz hipóteses fixas por preenchimento: 10 bps de taxa, 5 bps adicionais de incerteza e 0,02 USDC de gas. Estes números não foram confirmados como as tarifas ou slippage reais da Kuru. Preenchimentos podem ser otimistas apesar desse desconto. Custos do modelo reportados pela OpenRouter são descontados da conta Jev; chamadas sem custo reportado ficam identificadas e podem fazer o resultado parecer melhor.
- O prazo começa com uma cotação recente e continua durante pausas. O fechamento depende de nova cotação para marcar uma posição ainda aberta. Cinco dias permitem observar comportamento e perdas, mas não inferir a chance de transformar 1.000 em 10.000 USDC ao longo de 90 dias.

## Ainda não implementado no fluxo da aplicação

1. Criação/execução de experimentos PAPER A/B/C, vinculação persistente das três contas após preflight e aplicação da mesma configuração em contas isoladas.
2. Coleta central de bars/news PAPER com snapshots imutáveis, política de cutoff, detecção de lacunas degradadas e armazenamento de versões de notícia.
3. Orquestração de análise real B/C ligada a reservas de orçamento antes da chamada, custo desconhecido reconciliável, cache e controle de concorrência.
4. Worker operacional PAPER que persiste intenção, revalida controles/dado recente, envia/cancela, ingere eventos/fills idempotentes e retoma reconciliação após reinício. Há métodos do cliente HTTP isolado; eles não equivalem a esse fluxo.
5. REPLAY usando apenas respostas/snapshots gravados e livro próprio com hipóteses de execução explícitas.
6. Métricas comparativas PAPER, custo real atribuível a IA/infraestrutura, performance no intervalo comum e estado de degradação no dashboard.
7. Testes autenticados opt-in para as integrações externas e testes de integração PostgreSQL multi-worker. Nenhum deles foi executado.

## Limitações do DRY RUN Monad/Kuru

- A meta de 1.000 para 10.000 USDC em 90 dias exigiria cerca de 13,65% de crescimento composto nos primeiros cinco dias, se o ritmo fosse uniforme. Essa régua é matemática: um resultado de cinco dias não prevê os 85 dias restantes.
- O prazo de cinco dias começa na primeira cotação válida após ativar a simulação. Pausas não reiniciam o prazo. O fechamento usa a primeira cotação válida recebida no fim ou após o prazo; se o feed estiver indisponível, o resultado final fica pendente até chegar outra cotação.
- A conta é fictícia: começa com 1.000 USDC virtuais, limita cada ordem a 10 USDC, exige confiança mínima de 80%, permite só uma posição comprada e bloqueia vendas descobertas. Cada ordem limite expira após 120 segundos.
- Como só 10 USDC podem entrar por ordem e uma única posição comprada é permitida, este piloto mede o comportamento dos sinais e a mecânica local, não a viabilidade de aplicar 1.000 USDC nem de multiplicá-los por dez. A configuração não deve ser ampliada no meio de um piloto já iniciado sem criar um novo livro e registrar novas hipóteses.
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
