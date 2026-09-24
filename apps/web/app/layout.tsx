import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "PaperLab · Laboratório de estratégias",
  description: "Comparação rastreável de estratégias em simulação com dinheiro fictício.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
