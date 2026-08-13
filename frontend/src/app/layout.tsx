import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "客经智审",
  description: "SFA 门店拜访数据导入与审核",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
    >
      <body
        className="min-h-full flex flex-col"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
