import { useCallback, useEffect, useState } from "react";
import {
  ActionIcon,
  Alert,
  AppShell,
  Box,
  Burger,
  Button,
  Group,
  Loader,
  NavLink,
  Paper,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconAlertCircle,
  IconArrowUpRight,
  IconCalendarMonth,
  IconChartHistogram,
  IconDatabase,
  IconLayoutDashboard,
  IconPlus,
  IconRefresh,
  IconWallet,
} from "@tabler/icons-react";
import {
  getPortfolioOverview,
  type PortfolioStatus,
  type PortfolioSummary,
} from "./api/portfolio";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CalendarPage } from "./pages/CalendarPage";
import { DataPage } from "./pages/DataPage";
import { OverviewPage } from "./pages/OverviewPage";
import { OperationsPage } from "./pages/OperationsPage";

type OverviewState = { summary: PortfolioSummary; status: PortfolioStatus };
export type Tab = "overview" | "analytics" | "calendar" | "operations" | "data";

const tabs = [
  { id: "overview", label: "Обзор", description: "Главные показатели", icon: IconLayoutDashboard },
  { id: "analytics", label: "Аналитика", description: "Динамика и доходность", icon: IconChartHistogram },
  { id: "calendar", label: "Календарь", description: "Выплаты и погашения", icon: IconCalendarMonth },
  { id: "operations", label: "Операции", description: "Покупки и движение денег", icon: IconWallet },
  { id: "data", label: "Данные", description: "Синхронизация и бэкапы", icon: IconDatabase },
] as const;

export function App() {
  const [overview, setOverview] = useState<OverviewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [revision, setRevision] = useState(0);
  const [navOpened, navHandlers] = useDisclosure(false);

  const loadOverview = useCallback(async () => {
    setRefreshing(true);
    try {
      setOverview(await getPortfolioOverview());
      setError(null);
      setRevision((value) => value + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить портфель");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void loadOverview(); }, [loadOverview]);

  const navigate = (next: Tab) => {
    setTab(next);
    navHandlers.close();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const current = tabs.find((item) => item.id === tab)!;

  return (
    <AppShell
      header={{ height: 72 }}
      navbar={{ width: 272, breakpoint: "md", collapsed: { mobile: !navOpened } }}
      padding={0}
      className="portfolio-shell"
    >
      <AppShell.Header className="app-header">
        <Group h="100%" px={{ base: "md", md: "xl" }} justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={navOpened} onClick={navHandlers.toggle} hiddenFrom="md" size="sm" aria-label="Открыть меню" />
            <Box hiddenFrom="md">
              <Text fw={800} size="sm">Портфель</Text>
              <Text c="dimmed" size="xs">{current.label}</Text>
            </Box>
            <Box visibleFrom="md">
              <Text size="xs" c="dimmed" fw={600}>Личный капитал</Text>
              <Text fw={700}>{current.label}</Text>
            </Box>
          </Group>

          <Group gap="sm" wrap="nowrap">
            <Tooltip label="Обновить данные">
              <ActionIcon variant="default" size="lg" radius="md" onClick={() => void loadOverview()} loading={refreshing} aria-label="Обновить данные">
                <IconRefresh size={18} />
              </ActionIcon>
            </Tooltip>
            <Button visibleFrom="xs" leftSection={<IconPlus size={17} />} radius="md" onClick={() => navigate("operations")}>Операция</Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar className="app-navbar" p="md">
        <button className="wordmark" type="button" onClick={() => navigate("overview")}>
          <ThemeIcon size={42} radius={14} variant="gradient" gradient={{ from: "indigo", to: "cyan", deg: 135 }}>
            <IconChartHistogram size={22} stroke={2.2} />
          </ThemeIcon>
          <span><strong>Портфель</strong><small>финансы без шума</small></span>
        </button>

        <Stack gap={6} mt={34}>
          <Text className="nav-section-label">Рабочее пространство</Text>
          {tabs.map((item) => (
            <NavLink
              key={item.id}
              active={tab === item.id}
              label={item.label}
              description={item.description}
              leftSection={<item.icon size={20} stroke={1.8} />}
              onClick={() => navigate(item.id)}
              className="main-nav-link"
            />
          ))}
        </Stack>

        <Paper className="local-data-card" mt="auto" p="md" radius="lg">
          <Group gap="xs"><span className="status-pulse" /><Text size="xs" fw={700}>Работает локально</Text></Group>
          <Text size="xs" c="dimmed" mt={8} lh={1.5}>База и финансовые данные остаются на вашей машине.</Text>
          <Button component="a" href="/" variant="subtle" color="gray" size="compact-sm" mt="sm" px={0} rightSection={<IconArrowUpRight size={14} />}>Открыть старый интерфейс</Button>
        </Paper>
      </AppShell.Navbar>

      <AppShell.Main>
        <Box className="page-canvas">
          {error && (
            <Alert icon={<IconAlertCircle size={18} />} title="Не удалось обновить данные" color="red" radius="lg" mb="lg" withCloseButton onClose={() => setError(null)}>
              <Group justify="space-between"><Text size="sm">{error}</Text><Button size="compact-sm" color="red" variant="light" onClick={() => void loadOverview()}>Повторить</Button></Group>
            </Alert>
          )}
          {overview ? (
            <Page tab={tab} overview={overview} revision={revision} onNavigate={navigate} onChanged={loadOverview} />
          ) : <LoadingDashboard />}
        </Box>
      </AppShell.Main>

      <nav className="mobile-dock" aria-label="Разделы">
        {tabs.map((item) => (
          <button type="button" className={tab === item.id ? "active" : ""} onClick={() => navigate(item.id)} key={item.id}>
            <item.icon size={20} stroke={tab === item.id ? 2.3 : 1.8} /><span>{item.label}</span>
          </button>
        ))}
      </nav>
    </AppShell>
  );
}

function Page({ tab, overview, revision, onNavigate, onChanged }: { tab: Tab; overview: OverviewState; revision: number; onNavigate: (tab: Tab) => void; onChanged: () => Promise<void> }) {
  if (tab === "analytics") return <AnalyticsPage revision={revision} />;
  if (tab === "calendar") return <CalendarPage revision={revision} />;
  if (tab === "operations") return <OperationsPage revision={revision} onChanged={onChanged} />;
  if (tab === "data") return <DataPage status={overview.status} onChanged={onChanged} />;
  return <OverviewPage summary={overview.summary} status={overview.status} revision={revision} onNavigate={onNavigate} />;
}

function LoadingDashboard() {
  return <Stack align="center" justify="center" mih={420} gap="md"><Loader size="md" /><Title order={3}>Собираем финансовую картину</Title><Text c="dimmed" size="sm">Загружаем портфель и последние показатели</Text></Stack>;
}
