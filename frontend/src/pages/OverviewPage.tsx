import { useEffect, useState } from "react";
import { Button, Group, Paper, SimpleGrid, Text, Title } from "@mantine/core";
import { IconArrowRight, IconPlugConnected, IconPlus } from "@tabler/icons-react";
import type { Tab } from "../App";
import type { PortfolioStatus, PortfolioSummary } from "../api/portfolio";
import { getPositions, getReturns, type Position, type ReturnsData } from "../api/dashboard";
import { AllocationPanel } from "../components/AllocationPanel";
import { GoalCard } from "../components/GoalCard";
import { KpiGrid } from "../components/KpiGrid";
import { PageHeading } from "../components/PageHeading";
import { PositionsTable } from "../components/PositionsTable";
import { PerformanceStrip } from "../components/PerformanceStrip";
import { SystemStatus } from "../components/SystemStatus";
import { formatDate } from "../lib/format";

export function OverviewPage({summary,status,revision,onNavigate}:{summary:PortfolioSummary;status:PortfolioStatus;revision:number;onNavigate:(tab:Tab)=>void}) {
  const [positions,setPositions]=useState<Position[]>([]); const [returns,setReturns]=useState<ReturnsData|null>(null);
  useEffect(()=>{void Promise.all([getPositions(),getReturns("daily")]).then(([p,r])=>{setPositions(p);setReturns(r)})},[revision]);
  return <>
    <PageHeading eyebrow="Финансовая картина" title="Обзор портфеля" subtitle={`Актуальные данные на ${formatDate(summary.as_of)}`} actions={<Button variant="subtle" color="gray" rightSection={<IconArrowRight size={16}/>} onClick={()=>onNavigate("analytics")}>Открыть аналитику</Button>}/>
    {status.data.instruments===0&&<Paper className="onboarding-modern" radius="xl" p="xl"><Group justify="space-between" align="center"><div><Text className="section-kicker">Быстрый старт</Text><Title order={2}>Подключите реальные данные</Title><Text c="dimmed" mt="xs">Импортируйте T‑Invest или добавьте ручной актив. Всё хранится локально.</Text></div><Group><Button leftSection={<IconPlugConnected size={17}/>} onClick={()=>onNavigate("data")}>Импортировать</Button><Button variant="white" color="dark" leftSection={<IconPlus size={17}/>} onClick={()=>onNavigate("operations")}>Добавить операцию</Button></Group></Group></Paper>}
    <div className="dashboard-stack"><KpiGrid summary={summary}/><PerformanceStrip values={[{label:"Сегодня",delta:returns?.today},{label:"Неделя",delta:returns?.week},{label:"Месяц",delta:returns?.month},{label:"С начала года",delta:returns?.ytd}]}/><SimpleGrid cols={{base:1,lg:3}} spacing="md"><GoalCard current={summary.value} goal={status.portfolio_goal} streak={summary.streak}/><AllocationPanel classes={summary.by_class}/><SystemStatus status={status}/></SimpleGrid><Paper withBorder radius="lg" p={{base:"md",md:"xl"}}><Group justify="space-between"><div><Text className="section-kicker">Текущий состав</Text><Title order={3}>Позиции</Title></div><Text size="xs" c="dimmed">{positions.length} активов</Text></Group><PositionsTable positions={positions}/></Paper></div>
  </>;
}
