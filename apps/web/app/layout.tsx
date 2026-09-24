import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "PaperLab · Piloto de cinco dias",
  description: "Acompanhe por cinco dias uma carteira virtual de US$ 1.000 com dados reais da Kuru e decisões do Jev.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
