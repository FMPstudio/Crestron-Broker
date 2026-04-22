export type SourceNode = {
  deviceId: string;
  ip: string;
  active: boolean;
  connectedInput: number | null;
};

export type InputNode = {
  inputId: number;
  multicastIp: string;
  active: boolean;
  connectedDeviceId: string | null;
};

export type RouteEdge = {
  deviceId: string;
  inputId: number;
};

export type RoutingSnapshot = {
  sources: SourceNode[];
  inputs: InputNode[];
  routes: RouteEdge[];
  lastUpdated: string;
  errors: string[];
};


export type EdgePath = {
  id: string;
  d: string;
};
