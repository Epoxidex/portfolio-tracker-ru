import { Badge, Group, Paper, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconBuildingBank, IconCamera, IconCurrencyRubel, IconDatabase } from "@tabler/icons-react";
import type { PortfolioStatus } from "../api/portfolio";

const fxLabels = { cbr: "ЦБ РФ", bank_buy: "Банк покупает", bank_sell: "Банк продаёт" };
export function SystemStatus({ status }: { status: PortfolioStatus }) {
  const items = [
    { label:"Т‑Инвестиции", value:status.tinvest.configured?"Подключены":"Не подключены", ok:status.tinvest.configured, icon:IconBuildingBank },
    { label:"Источник валют", value:fxLabels[status.fx_source], ok:true, icon:IconCurrencyRubel },
    { label:"Снимки портфеля", value:String(status.data.snapshots), ok:status.data.snapshots>0, icon:IconCamera },
    { label:"Операции в базе", value:String(status.data.transactions), ok:status.data.transactions>0, icon:IconDatabase },
  ];
  return <Paper withBorder radius="lg" p="xl" className="feature-card"><Group justify="space-between"><div><Text className="section-kicker">Система</Text><Title order={3}>Состояние данных</Title></div><Badge color="teal" variant="light">Локально</Badge></Group><Stack gap={0} mt="lg">{items.map(item=><Group className="status-item" key={item.label} justify="space-between" wrap="nowrap"><Group gap="sm" wrap="nowrap"><ThemeIcon variant="light" color={item.ok?"indigo":"gray"} radius="md"><item.icon size={17}/></ThemeIcon><Text size="sm" c="dimmed">{item.label}</Text></Group><Text size="sm" fw={700}>{item.value}</Text></Group>)}</Stack></Paper>;
}
