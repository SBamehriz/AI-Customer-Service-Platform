import { AtSign, Camera, Code, Mail, MessageCircle, MessageSquare, PhoneCall, Radio } from '@/components/icons';
import type { Channel } from '@/lib/types';

const ICONS: Record<Channel, React.ComponentType<{ className?: string }>> = {
  web: MessageSquare,
  email: Mail,
  whatsapp: Radio,
  instagram: Camera,
  sms: MessageCircle,
  voice: PhoneCall,
  api: Code,
};

export interface ChannelIconProps {
  channel: Channel;
  className?: string;
}

/** One glyph per channel, used everywhere a channel is shown. */
export function ChannelIcon({ channel, className }: ChannelIconProps) {
  const Icon = ICONS[channel] ?? AtSign;
  return <Icon className={className} />;
}
