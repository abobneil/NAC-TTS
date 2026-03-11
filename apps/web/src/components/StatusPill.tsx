type Props = {
  status: string;
};

export function StatusPill({ status }: Props) {
  return <span className={`status-pill status-${status}`}>{status}</span>;
}
