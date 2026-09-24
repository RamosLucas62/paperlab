# Experimentos e leitura dos resultados

## A/B/C na DEMO

- **A**: candidato SMA 20/50 + controles determinísticos.
- **B**: mesma estratégia + filtro textual sintético que exercita a política versionada.
- **C**: resumo textual sintético + o mesmo filtro que B.

As diferenças de filtro são artificiais e reprodutíveis. As notícias e preços da DEMO não vieram do mercado. Um evento de segurança fictício ilustra um veto de B/C; A permanece sem filtro. Sem texto novo, B/C seguem a baseline por política. Saídas da posição são iguais e independentes de texto. O modo não isola o efeito de geração sem JEV.

## Configuração congelada e registros

Cada DEMO persiste configuração/hash, semente, política, versão de custo, fonte e snapshots por ciclo. O cutoff fica no snapshot e as fontes são ligadas por ID. Decisões separam candidato, filtro, controle de carteira e resultado. Intenções e fills usam IDs únicos. Exportações JSON/CSV são protegidas por login e não incluem segredos.

## Métricas disponíveis

O painel DEMO exibe caixa, quantidade/valor de posição, patrimônio, retorno desde caixa inicial, drawdown em USD, exposição, contagem de intenções, operações encerradas, taxa de acerto quando há encerramentos, ganhos/perdas médios, custo sintético, vetos, abstenções, falhas, latência registrada e curvas de patrimônio. Mostra amostra insuficiente sem operações encerradas, mais referência de caixa parado e comprar/manter. Esses benchmarks herdam o caráter inteiramente sintético.

Não anualize amostras pequenas e não interprete confidence de classificação como chance de lucro. Custos API/infraestrutura da integração ainda não aparecem como consumo real no painel, pois as chamadas não foram conectadas à execução de experimentos.

## PAPER e REPLAY

O preflight Alpaca é separado do experimento e de somente leitura. Nenhum fluxo atual congela três contas e configurações para iniciar A/B/C PAPER. O worker não coleta candles/notícias reais e não chama os modelos. REPLAY com livro de simulação separado também ainda não está implementado. Assim, não compare esses dados DEMO com contas da corretora e não use DEMO como resultado de mercado.
