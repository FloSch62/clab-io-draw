class Node:
    """
    Represents a single node in the topology.
    """

    def __init__(
        self,
        name,
        label,
        kind,
        mgmt_ipv4=None,
        graph_level=None,
        graph_icon=None,
        **kwargs,
    ):
        self.name = name
        self.label = label
        self.kind = kind
        self.mgmt_ipv4 = mgmt_ipv4

        # Fix for level detection - a default of None is better than -1
        if graph_level is not None:
            try:
                self.graph_level = int(graph_level)
            except (ValueError, TypeError):
                self.graph_level = None
        else:
            self.graph_level = None

        self.graph_icon = graph_icon
        self.base_style = kwargs.get("base_style", "")
        self.custom_style = kwargs.get("custom_style", "")
        self.width = kwargs.get("width", "")
        self.height = kwargs.get("height", "")
        # Convert pos_x to float if possible, otherwise set to None
        pos_x = kwargs.get("pos_x")
        if pos_x is not None and pos_x != "":
            try:
                self.pos_x = int(float(pos_x))
            except (ValueError, TypeError):
                self.pos_x = None
        else:
            self.pos_x = None

        # Convert pos_y to float if possible, otherwise set to None
        pos_y = kwargs.get("pos_y")
        if pos_y is not None and pos_y != "":
            try:
                self.pos_y = int(float(pos_y))
            except (ValueError, TypeError):
                self.pos_y = None
        else:
            self.pos_y = None

        self.links = []
        self.group = kwargs.get("group", "")

    def add_link(self, link):
        self.links.append(link)

    def get_connection_count(self):
        return len(self.links)

    def get_connection_count_within_level(self):
        return len(
            [
                link
                for link in self.links
                if link.source.graph_level == self.graph_level
                or link.target.graph_level == self.graph_level
            ]
        )

    def get_downstream_links(self):
        return [link for link in self.links if link.direction == "downstream"]

    def get_upstream_links(self):
        return [link for link in self.links if link.direction == "upstream"]

    def get_upstream_links_towards_level(self, level):
        return [
            link
            for link in self.links
            if link.direction == "upstream" and link.target.graph_level == level
        ]

    def get_lateral_links(self):
        return [link for link in self.links if link.direction == "lateral"]

    def get_all_links(self):
        return self.links

    def get_neighbors(self):
        neighbors = set()
        for link in self.get_all_links():
            if link.source.name == self.name:
                neighbors.add(link.target)
            else:
                neighbors.add(link.source)
        return list(neighbors)

    def is_connected_to(self, other_node):
        for link in self.links:
            if link.source == other_node or link.target == other_node:
                return True
        return False

    def set_base_style(self, style):
        self.base_style = style

    def set_custom_style(self, style):
        self.custom_style = style

    def generate_style_string(self):
        style = f"{self.base_style}{self.custom_style}"
        style += f"pos_x={self.pos_x};pos_y={self.pos_y};"
        style += f"width={self.width};height={self.height};"
        return style

    def update_links(self):
        for link in self.links:
            source_level = link.source.graph_level
            target_level = link.target.graph_level
            link.level_diff = target_level - source_level
            if link.level_diff > 0:
                link.direction = "downstream"
            elif link.level_diff < 0:
                link.direction = "upstream"
            else:
                link.direction = "lateral"

    def __repr__(self):
        return f"Node(name='{self.name}', kind='{self.kind}')"
