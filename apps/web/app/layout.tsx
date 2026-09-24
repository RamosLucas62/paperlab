import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "PaperLab · Terminal JEV e simulação",
  description: "Terminal observacional Monad/Kuru e laboratório de estratégias em DEMO.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
