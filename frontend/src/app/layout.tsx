import type { Metadata } from "next";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Alzheimer Safety Dashboard",
  description: "Patient and caregiver dashboard for medicine reminders, familiar faces, and hazard alerts.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
