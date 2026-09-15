import { Monitor, Moon, Sun } from '@/components/icons';
import { Button, Tooltip } from '@/components/ui';
import { useTheme, type ThemeChoice } from '@/app/theme';

const ORDER: ThemeChoice[] = ['system', 'light', 'dark'];

const LABEL: Record<ThemeChoice, string> = {
  system: 'Following the system',
  light: 'Light',
  dark: 'Dark',
};

/** Cycles system, light, dark. */
export function ThemeToggle({ side = 'bottom' }: { side?: 'top' | 'bottom' }) {
  const { choice, setChoice } = useTheme();
  const Icon = choice === 'light' ? Sun : choice === 'dark' ? Moon : Monitor;

  return (
    <Tooltip label={LABEL[choice]} side={side}>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Theme, ${LABEL[choice].toLowerCase()}. Activate to change.`}
        onClick={() => setChoice(ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length])}
      >
        <Icon className="h-4 w-4" />
      </Button>
    </Tooltip>
  );
}
