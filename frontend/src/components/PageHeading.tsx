import type { ReactNode } from "react";

type PageHeadingProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  actions?: ReactNode;
};

export function PageHeading({ eyebrow, title, subtitle, actions }: PageHeadingProps) {
  return (
    <section className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </section>
  );
}
