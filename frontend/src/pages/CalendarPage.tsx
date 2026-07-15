import { useEffect, useMemo, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import listPlugin from "@fullcalendar/list";
import interactionPlugin from "@fullcalendar/interaction";
import ruLocale from "@fullcalendar/core/locales/ru";
import type { DatesSetArg, EventClickArg, EventContentArg } from "@fullcalendar/core";
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Divider,
  Drawer,
  Group,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArrowRight,
  IconCalendarEvent,
  IconCash,
  IconChevronRight,
  IconPigMoney,
  IconReceipt2,
  IconTrendingUp,
} from "@tabler/icons-react";
import { getCalendar, getPassiveIncome, type CalendarEvent, type PassiveIncome } from "../api/dashboard";
import { PageHeading } from "../components/PageHeading";
import { formatDate, formatMoney, todayInMoscow } from "../lib/format";

const TYPE_STYLE: Record<string, { color: string; hex: string; soft: string; icon: typeof IconCash }> = {
  "Купон": { color: "teal", hex: "#0ca678", soft: "#e6fcf5", icon: IconReceipt2 },
  "Проценты": { color: "orange", hex: "#f08c00", soft: "#fff4e6", icon: IconTrendingUp },
  "Дивиденд": { color: "violet", hex: "#7950f2", soft: "#f3f0ff", icon: IconCash },
  "Погашение": { color: "blue", hex: "#1c7ed6", soft: "#e7f5ff", icon: IconCalendarEvent },
  "Возврат вклада": { color: "indigo", hex: "#4c6ef5", soft: "#edf2ff", icon: IconPigMoney },
};
const fallback = { color: "cyan", hex: "#1098ad", soft: "#e3fafc", icon: IconCash };

export function CalendarPage({ revision }: { revision: number }) {
  const calendarRef = useRef<FullCalendar | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [income, setIncome] = useState<PassiveIncome>({ annual: 0, monthly: 0, detail: [] });
  const [showPast, setShowPast] = useState(false);
  const [view, setView] = useState("dayGridMonth");
  const [title, setTitle] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });
  const [selected, setSelected] = useState<CalendarEvent | null>(null);

  useEffect(() => { void Promise.all([getCalendar(), getPassiveIncome()]).then(([calendar, passive]) => { setEvents(calendar); setIncome(passive); }); }, [revision]);
  const today = todayInMoscow();
  const visible = useMemo(() => events.filter(event => showPast || event.date >= today), [events, showPast, today]);
  const calendarEvents = useMemo(() => visible.map((event, index) => {
    const style = TYPE_STYLE[event.type] || fallback;
    return { id: `${event.date}-${event.instrument}-${index}`, title: event.instrument, date: event.date, allDay: true, backgroundColor: style.soft, borderColor: style.soft, textColor: style.hex, extendedProps: { source: event } };
  }), [visible]);
  const upcoming = visible.filter(event => event.date >= today).slice(0, 6);
  const monthEvents = visible.filter(event => (!range.start || event.date >= range.start) && (!range.end || event.date < range.end));
  const monthTotal = monthEvents.reduce((sum, event) => sum + event.amount, 0);

  const changeView = (next: string) => { setView(next); calendarRef.current?.getApi().changeView(next); };
  const datesSet = (arg: DatesSetArg) => { setTitle(arg.view.title); setRange({ start: arg.startStr.slice(0, 10), end: arg.endStr.slice(0, 10) }); };
  const eventClick = (arg: EventClickArg) => setSelected(arg.event.extendedProps.source as CalendarEvent);

  return <>
    <PageHeading eyebrow="Денежный поток" title="Календарь выплат" subtitle="Купоны, дивиденды, проценты, возвраты вкладов и погашения — в одной временной картине" actions={<Switch checked={showPast} onChange={event => setShowPast(event.currentTarget.checked)} label="Показывать прошедшие"/>}/>

    <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" mb="md">
      <SummaryCard icon={IconCalendarEvent} color="indigo" label="В этом месяце" value={formatMoney(monthTotal)} detail={`${monthEvents.length} событий`} />
      <SummaryCard icon={IconCash} color="teal" label="Средний пассивный доход" value={formatMoney(income.monthly)} detail="в месяц" />
      <SummaryCard icon={IconTrendingUp} color="violet" label="Ожидается за год" value={formatMoney(income.annual)} detail="до налогов" />
    </SimpleGrid>

    <div className="calendar-workspace">
      <Paper withBorder radius="xl" className="calendar-card">
        <Group className="calendar-toolbar" justify="space-between" wrap="wrap" gap="md">
          <Group gap="xs">
            <Tooltip label="Предыдущий период"><ActionIcon variant="default" size="lg" radius="md" onClick={() => calendarRef.current?.getApi().prev()}><IconArrowLeft size={17}/></ActionIcon></Tooltip>
            <Button variant="default" radius="md" onClick={() => calendarRef.current?.getApi().today()}>Сегодня</Button>
            <Tooltip label="Следующий период"><ActionIcon variant="default" size="lg" radius="md" onClick={() => calendarRef.current?.getApi().next()}><IconArrowRight size={17}/></ActionIcon></Tooltip>
          </Group>
          <Title order={2} className="calendar-title">{title}</Title>
          <SegmentedControl value={view} onChange={changeView} data={[{ value: "dayGridMonth", label: "Месяц" }, { value: "listMonth", label: "Список" }]} />
        </Group>
        <Divider />
        <Box className="full-calendar-wrap">
          <FullCalendar
            ref={calendarRef}
            plugins={[dayGridPlugin, listPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            locale={ruLocale}
            firstDay={1}
            fixedWeekCount={false}
            showNonCurrentDates
            dayMaxEvents={3}
            height="auto"
            headerToolbar={false}
            events={calendarEvents}
            eventClick={eventClick}
            datesSet={datesSet}
            eventContent={renderEvent}
            noEventsContent="В этом периоде выплат нет"
          />
        </Box>
        <Group className="calendar-legend" gap="lg" wrap="wrap">{Object.entries(TYPE_STYLE).map(([name, style]) => <Group key={name} gap={6}><span style={{width:8,height:8,borderRadius:99,background:style.hex}}/><Text size="xs" c="dimmed">{name}</Text></Group>)}</Group>
      </Paper>

      <Stack gap="md">
        <Paper withBorder radius="xl" p="lg">
          <Group justify="space-between" mb="md"><div><Text className="section-kicker">На горизонте</Text><Title order={3}>Ближайшие выплаты</Title></div><Badge variant="light">{upcoming.length}</Badge></Group>
          <Stack gap={0}>{upcoming.length ? upcoming.map((event, index) => <UpcomingEvent event={event} key={`${event.date}-${event.instrument}-${index}`} onClick={() => setSelected(event)} />) : <Text c="dimmed" size="sm" ta="center" py={48}>Будущих выплат пока нет</Text>}</Stack>
        </Paper>
        <Paper withBorder radius="xl" p="lg">
          <Text className="section-kicker">Run-rate</Text><Title order={3}>Источники дохода</Title>
          <Stack gap={0} mt="md">{income.detail.length ? income.detail.slice().sort((a,b)=>b.annual-a.annual).slice(0,7).map(item => <Group className="income-row" key={item.name} justify="space-between" wrap="nowrap"><div><Text size="sm" fw={700}>{item.name}</Text><Text size="xs" c="dimmed">{formatMoney(item.annual/12)} в месяц</Text></div><Text size="sm" fw={750}>{formatMoney(item.annual)}</Text></Group>) : <Text c="dimmed" size="sm" ta="center" py={36}>Источников пока нет</Text>}</Stack>
        </Paper>
      </Stack>
    </div>

    <Drawer opened={selected !== null} onClose={() => setSelected(null)} position="right" size="sm" title="Детали выплаты" padding="xl">
      {selected && <EventDetails event={selected}/>} 
    </Drawer>
  </>;
}

function renderEvent(arg: EventContentArg) {
  const event = arg.event.extendedProps.source as CalendarEvent;
  return <div className="calendar-event-content"><span>{event.instrument}</span><strong>{formatMoney(event.amount)}</strong></div>;
}
function SummaryCard({icon:Icon,color,label,value,detail}:{icon:typeof IconCash;color:string;label:string;value:string;detail:string}) { return <Paper withBorder radius="lg" p="lg"><Group wrap="nowrap"><ThemeIcon variant="light" color={color} size={44} radius="md"><Icon size={21}/></ThemeIcon><div><Text size="xs" c="dimmed" fw={650}>{label}</Text><Text size="xl" fw={780} className="summary-value">{value}</Text><Text size="xs" c="dimmed">{detail}</Text></div></Group></Paper>; }
function UpcomingEvent({event,onClick}:{event:CalendarEvent;onClick:()=>void}) { const style=TYPE_STYLE[event.type]||fallback; const Icon=style.icon; return <button className="upcoming-event" type="button" onClick={onClick}><ThemeIcon variant="light" color={style.color} radius="md"><Icon size={17}/></ThemeIcon><span><Text size="sm" fw={700} lineClamp={1}>{event.instrument}</Text><Text size="xs" c="dimmed">{formatDate(event.date)} · {event.type}</Text></span><span><Text size="sm" fw={750}>{formatMoney(event.amount)}</Text><IconChevronRight size={15}/></span></button>; }
function EventDetails({event}:{event:CalendarEvent}) { const style=TYPE_STYLE[event.type]||fallback; const Icon=style.icon; return <Stack gap="xl"><Paper radius="xl" p="xl" style={{background:style.soft}}><ThemeIcon color={style.color} variant="filled" size={48} radius="lg"><Icon size={23}/></ThemeIcon><Text c={style.color} size="sm" fw={750} mt="lg">{event.type}</Text><Title order={2} mt={4}>{event.instrument}</Title><Text className="drawer-amount" mt="xl">{formatMoney(event.amount)}</Text></Paper><Stack gap="md"><DetailRow label="Дата выплаты" value={formatDate(event.date)}/><DetailRow label="Инструмент" value={event.ticker||event.instrument}/><DetailRow label="Тип события" value={event.type}/></Stack><Text size="xs" c="dimmed" lh={1.6}>Будущие события являются прогнозом. Фактическое зачисление отражается отдельной операцией или после синхронизации с брокером.</Text></Stack>; }
function DetailRow({label,value}:{label:string;value:string}) { return <Group justify="space-between" wrap="nowrap"><Text size="sm" c="dimmed">{label}</Text><Text size="sm" fw={700} ta="right">{value}</Text></Group>; }
