"""
Advanced Analyzer za FPGA_Visualizer
===================================

Ovaj modul sadržI klasu `AdvancedAnalyzer` koja prikuplja napredne analize
nad grafom, signalima i routing podacima.

Pretpostavke o inputima (fleksibilne):
- `graph` je networkx Graph/DiGraph gde node-ovi mogu imati atribute (npr. pos, tile)
- `signals` je lista dict-ova ili objekata sa bar poljima: `name`, `endpoints`, `path`, `wire_length`
  * `endpoints`: list/tuple od 2 node id-a (source, sink) ili lista tačaka
  * `path`: lista node id-ova koja opisuje rutu (može biti prazno ako nije dostupno)
  * `wire_length`: numerička vrednost (ako postoji)
- `routing_data` je dict sa dodatnim informacijama npr. `edge_congestion` mapa (edge -> value)

Zahtevi zavise od biblioteka: koristi se numpy, networkx, scikit-learn (KMeans).
Ako nisu u projektu - dodati u requirements.txt: numpy, networkx, scikit-learn

"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import networkx as nx
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
import warnings


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class SubgraphNSAnalysisResult:
    n: int
    subgraphs_count: int
    sizes: List[int]
    densitites: List[float]
    top_subgraphs: List[List[Any]] = field(default_factory=list)


@dataclass
class EndpointOffsetResult:
    avg_offset: float
    max_offset: float
    offsets: List[float]
    per_signal: Dict[str, float] = field(default_factory=dict)


@dataclass
class CongestionEvolutionResult:
    iterations: int
    mean_per_iter: List[float]
    trend_slope: float
    trend_intercept: float


@dataclass
class SignalClusterResult:
    n_clusters: int
    labels: List[int]
    centroids: List[List[float]]


@dataclass
class RoutingComplexityResult:
    avg_degree: float
    avg_path_length: float
    path_length_std: float
    congestion_entropy: float


@dataclass
class OptimizationRecommendation:
    priority: str  # 'HIGH','MEDIUM','LOW'
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdvancedAnalysisReport:
    subgraph_ns: Optional[SubgraphNSAnalysisResult] = None
    endpoint_offsets: Optional[EndpointOffsetResult] = None
    congestion_evolution: Optional[CongestionEvolutionResult] = None
    signal_clusters: Optional[SignalClusterResult] = None
    routing_complexity: Optional[RoutingComplexityResult] = None
    recommendations: List[OptimizationRecommendation] = field(default_factory=list)


class AdvancedAnalyzer:
    """Napredni analitičar za FPGA vizualizacije.

    Primer upotrebe:

        analyzer = AdvancedAnalyzer(graph, signals, routing_data)
        report = analyzer.run_all()

    Metode su dizajnirane da budu samostalne i mogu se pozivati pojedinačno.
    """

    def __init__(
        self,
        graph: nx.Graph,
        signals: Iterable[Dict[str, Any]],
        routing_data: Optional[Dict[str, Any]] = None,
    ):
        self.graph = graph
        # normalize signals to a list of dicts
        self.signals = list(signals) if signals is not None else []
        self.routing_data = routing_data or {}

    # -------------------------- helpers --------------------------
    @staticmethod
    def _safe_get_path_length(signal: Dict[str, Any]) -> float:
        # prefer explicit wire_length, else fallback to len(path)-1
        if signal.get("wire_length") is not None:
            return float(signal["wire_length"])
        path = signal.get("path") or []
        return float(max(0, len(path) - 1))

    @staticmethod
    def _euclidean_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        ax, ay = a
        bx, by = b
        return float(np.hypot(ax - bx, ay - by))

    # -------------------------- analyses --------------------------
    def subgraph_ns_analysis(self, n: int = 2, top_k: int = 5) -> SubgraphNSAnalysisResult:
        """n-SB analiza podgrafa — pronalazi i rangira podgrafe oko signala.

        Implementacija:
        - za svaki signal uzimamo okolinu (n-hop) oko njegovih krajnjih tačaka
        - spajamo okolne node-ove u lokalni podgraf
        - merimo veličinu i gustinu
        - vračamo top K po veličini
        """
        subgraphs = []
        for sig in self.signals:
            endpoints = sig.get("endpoints") or []
            # podržimo jedan ili dva endpointa
            nodes_set = set()
            for ep in endpoints[:2]:
                if ep in self.graph:
                    nodes = nx.single_source_shortest_path_length(self.graph, ep, cutoff=n).keys()
                    nodes_set.update(nodes)
            if nodes_set:
                subg = self.graph.subgraph(nodes_set).copy()
                subgraphs.append(subg)

        sizes = [g.number_of_nodes() for g in subgraphs]
        dens = [nx.density(g) if g.number_of_nodes() > 0 else 0.0 for g in subgraphs]

        # top_k subgraphs by size
        sorted_idx = np.argsort(sizes)[::-1][:top_k]
        top_subgraphs = [list(subgraphs[i].nodes()) for i in sorted_idx if i < len(subgraphs)]

        res = SubgraphNSAnalysisResult(
            n=n,
            subgraphs_count=len(subgraphs),
            sizes=sizes,
            densitites=dens,
            top_subgraphs=top_subgraphs,
        )
        logger.info("subgraph_ns_analysis finished: %s", res)
        return res

    def endpoint_offset_analysis(self, coordinate_attr: str = "pos") -> EndpointOffsetResult:
        """Analiza ofseta krajnjih tačaka.

        Očekivano: nodes u grafu imaju atribut `coordinate_attr` = (x,y).
        Za svaki signal uzmemo srednju tačku iz `path` (ili endpoint poziciju ako postoji)
        i izmerimo udaljenost između endpointa signala i node pozicija.
        """
        offsets = []
        per_signal = {}

        for sig in self.signals:
            name = sig.get("name", "unnamed")
            endpoints = sig.get("endpoints") or []
            # ako endpoints imaju koordinate direktno
            local_offsets = []
            for ep in endpoints[:2]:
                # ep može biti node id ili koordinata tuple
                if isinstance(ep, (list, tuple)) and len(ep) == 2 and not (ep in self.graph):
                    # tuple coords
                    # attempt to match to nearest node
                    coords = tuple(ep)
                    # find nearest node that has coordinates
                    best = None
                    best_d = float("inf")
                    for n, d in self.graph.nodes(data=True):
                        pos = d.get(coordinate_attr)
                        if pos:
                            try:
                                dist = self._euclidean_distance(coords, tuple(pos))
                            except Exception:
                                continue
                            if dist < best_d:
                                best_d = dist
                                best = n
                    if best is not None:
                        local_offsets.append(float(best_d))
                else:
                    # ep is probably a node id
                    node = ep
                    if node in self.graph:
                        node_pos = self.graph.nodes[node].get(coordinate_attr)
                        # try to pick representative coordinate from signal path
                        path = sig.get("path") or []
                        rep = None
                        if path:
                            # take middle point of path that has coordinates
                            mid = path[len(path) // 2]
                            rep = self.graph.nodes.get(mid, {}).get(coordinate_attr)
                        if rep and node_pos:
                            try:
                                d = self._euclidean_distance(tuple(node_pos), tuple(rep))
                                local_offsets.append(float(d))
                            except Exception:
                                continue
            if local_offsets:
                mean_off = float(np.mean(local_offsets))
                offsets.extend(local_offsets)
                per_signal[name] = mean_off

        if offsets:
            avg = float(np.mean(offsets))
            mx = float(np.max(offsets))
        else:
            avg = 0.0
            mx = 0.0

        res = EndpointOffsetResult(avg_offset=avg, max_offset=mx, offsets=offsets, per_signal=per_signal)
        logger.info("endpoint_offset_analysis finished: %s", res)
        return res

    def congestion_evolution(self, congestion_history: Optional[List[np.ndarray]] = None) -> CongestionEvolutionResult:
        """Analiza evolucije zagušenja kroz iteracije.

        `congestion_history` je lista 2D numpy nizova (grid) ili lista 1D lista metrika.
        Ako nije prosleđeno, pokušava da ga uzme iz routing_data['congestion_history']
        """
        if congestion_history is None:
            congestion_history = self.routing_data.get("congestion_history")

        if not congestion_history:
            # fallback: ako routing_data sadrzi edge_congestion per iter
            per_iter = self.routing_data.get("per_iter_mean_congestion")
            if per_iter:
                mean_per_iter = list(map(float, per_iter))
            else:
                mean_per_iter = []
        else:
            mean_per_iter = []
            for grid in congestion_history:
                arr = np.array(grid)
                mean_per_iter.append(float(np.nanmean(arr)))

        iterations = len(mean_per_iter)
        if iterations >= 2:
            x = np.arange(iterations)
            y = np.array(mean_per_iter)
            # linear trend
            slope, intercept = np.polyfit(x, y, 1)
        else:
            slope = 0.0
            intercept = mean_per_iter[0] if mean_per_iter else 0.0

        res = CongestionEvolutionResult(iterations=iterations, mean_per_iter=mean_per_iter, trend_slope=float(slope), trend_intercept=float(intercept))
        logger.info("congestion_evolution finished: %s", res)
        return res

    def signal_cluster_analysis(self, n_clusters: int = 4, features: Optional[List[str]] = None, random_state: int = 0) -> SignalClusterResult:
        """Klaster analiza signala koristeći KMeans.

        Podrazumevane karakteristike se grade iz signala:
        - wire_length (ako postoji)
        - path_length (len(path))
        - avg_edge_congestion na putu (ako routing_data ima edge_congestion map)
        - degree susedstva (prosečan stepen krajnjih tačaka)

        Vraća label-e i centroids.
        """
        if features is None:
            features = ["wire_length", "path_len", "avg_edge_cong", "endpoint_degree"]

        X = []
        names = []
        edge_cong_map = self.routing_data.get("edge_congestion", {})

        for sig in self.signals:
            names.append(sig.get("name", "unnamed"))
            vals = []
            # wire_length
            wl = sig.get("wire_length")
            if wl is None:
                wl = self._safe_get_path_length(sig)
            vals.append(float(wl))
            # path_len
            path_len = len(sig.get("path") or [])
            vals.append(float(path_len))
            # avg_edge_cong
            path = sig.get("path") or []
            if path and len(path) > 1:
                edge_vals = []
                for a, b in zip(path[:-1], path[1:]):
                    e = (a, b)
                    # undirected fallback
                    if e not in edge_cong_map and (b, a) in edge_cong_map:
                        e = (b, a)
                    v = edge_cong_map.get(e, 0.0)
                    edge_vals.append(float(v))
                avg_edge = float(np.mean(edge_vals)) if edge_vals else 0.0
            else:
                avg_edge = 0.0
            vals.append(avg_edge)
            # endpoint degree
            endpoints = sig.get("endpoints") or []
            degs = []
            for ep in endpoints[:2]:
                if ep in self.graph:
                    degs.append(self.graph.degree(ep))
            ep_deg = float(np.mean(degs)) if degs else 0.0
            vals.append(ep_deg)

            X.append(vals)

        X = np.array(X, dtype=float) if X else np.zeros((0, len(features)))

        if X.shape[0] == 0:
            return SignalClusterResult(n_clusters=0, labels=[], centroids=[])

        # normalize features to zero mean unit var to help clustering
        X_mean = X.mean(axis=0)
        X_std = X.std(axis=0)
        X_std[X_std == 0] = 1.0
        Xn = (X - X_mean) / X_std

        # choose n_clusters not greater than samples
        k = min(n_clusters, Xn.shape[0])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            kmeans = KMeans(n_clusters=k, random_state=random_state, n_init=10)
            labels = kmeans.fit_predict(Xn)

        centroids = (kmeans.cluster_centers_ * X_std + X_mean).tolist()

        res = SignalClusterResult(n_clusters=k, labels=labels.tolist(), centroids=centroids)
        logger.info("signal_cluster_analysis finished: clusters=%d", k)
        return res

    def routing_complexity(self) -> RoutingComplexityResult:
        """Analiza kompleksnosti rutiranja.

        Metrike:
        - prosečan stepen grafa
        - prosečna dužina puteva (iz signala)
        - standardna devijacija dužine puteva
        - entropija zagušenja na ivicama (ako postoji edge_congestion)
        """
        degrees = [d for n, d in self.graph.degree()]
        avg_deg = float(np.mean(degrees)) if degrees else 0.0

        path_lengths = [self._safe_get_path_length(s) for s in self.signals]
        if path_lengths:
            avg_pl = float(np.mean(path_lengths))
            std_pl = float(np.std(path_lengths))
        else:
            avg_pl = 0.0
            std_pl = 0.0

        edge_cong = list(self.routing_data.get("edge_congestion", {}).values())
        if edge_cong:
            # normalize to probabilities and compute entropy
            arr = np.array(edge_cong, dtype=float)
            if np.any(arr < 0):
                arr = arr - arr.min()  # shift
            s = arr.sum()
            if s == 0:
                entropy = 0.0
            else:
                p = arr / s
                entropy = float(-np.sum([x * np.log2(x) for x in p if x > 0]))
        else:
            entropy = 0.0

        res = RoutingComplexityResult(avg_degree=avg_deg, avg_path_length=avg_pl, path_length_std=std_pl, congestion_entropy=entropy)
        logger.info("routing_complexity finished: %s", res)
        return res

    # -------------------------- recommendations --------------------------
    def generate_optimization_recommendations(self, report: Optional[AdvancedAnalysisReport] = None) -> List[OptimizationRecommendation]:
        """Na osnovu izvšenih analiza dajemo preporuke.

        Logika je heuristička:
        - ako trend zagušenja raste -> HIGH priority re-routing / binning
        - ako avg_offset velika -> VALIDATE placement / pin assignment
        - ako cluster pokazuje "težk" cluster -> spojiti signale / prioritizovati
        - ako entropy zagušenja velika -> redistribucija
        """
        recomms: List[OptimizationRecommendation] = []

        if report is None:
            # pokreni osnovne analize
            report = AdvancedAnalysisReport()
            report.congestion_evolution = self.congestion_evolution()
            report.endpoint_offsets = self.endpoint_offset_analysis()
            report.routing_complexity = self.routing_complexity()
            report.signal_clusters = self.signal_cluster_analysis()

        # 1. congestion trend
        ce = report.congestion_evolution
        if ce and ce.trend_slope > 0.001:
            recomms.append(
                OptimizationRecommendation(
                    priority="HIGH",
                    message="Rising congestion trend detected — consider re-routing hot areas and spreading placement.",
                    details={"trend_slope": ce.trend_slope, "mean_per_iter": ce.mean_per_iter},
                )
            )
        elif ce and ce.trend_slope > 0:
            recomms.append(
                OptimizationRecommendation(
                    priority="MEDIUM",
                    message="Mild positive congestion trend — monitor or apply incremental optimizations.",
                    details={"trend_slope": ce.trend_slope},
                )
            )

        # 2. endpoint offsets
        eo = report.endpoint_offsets
        if eo and eo.avg_offset > 5.0:  # threshold in "distance units" - prilagoditi
            recomms.append(
                OptimizationRecommendation(
                    priority="HIGH",
                    message="Large endpoint offsets — validate placement and pin mapping; consider physical constraints.",
                    details={"avg_offset": eo.avg_offset, "max_offset": eo.max_offset},
                )
            )
        elif eo and eo.avg_offset > 1.0:
            recomms.append(
                OptimizationRecommendation(
                    priority="LOW",
                    message="Non-trivial endpoint offsets — small placement adjustments may help.",
                    details={"avg_offset": eo.avg_offset},
                )
            )

        # 3. routing complexity
        rc = report.routing_complexity
        if rc:
            if rc.congestion_entropy > 6.0:
                recomms.append(
                    OptimizationRecommendation(
                        priority="HIGH",
                        message="High congestion entropy — congestion is widespread and unpredictable. Consider re-partitioning the design or using different routing strategies.",
                        details={"congestion_entropy": rc.congestion_entropy},
                    )
                )
            if rc.avg_path_length > 200:
                recomms.append(
                    OptimizationRecommendation(
                        priority="MEDIUM",
                        message="Average wire lengths are high — examine long nets for pipelining or partitioning.",
                        details={"avg_path_length": rc.avg_path_length},
                    )
                )

        # 4. signal clusters — find large clusters with high wire length
        sc = report.signal_clusters
        if sc and sc.n_clusters > 0:
            # gather cluster stats
            labels = np.array(sc.labels)
            # compute approx cluster sizes
            unique, counts = np.unique(labels, return_counts=True)
            big_clusters = unique[counts > max(5, int(0.1 * len(labels)))] if len(labels) > 0 else []
            if len(big_clusters) > 0:
                recomms.append(
                    OptimizationRecommendation(
                        priority="MEDIUM",
                        message="Detected big clusters of signals — consider logical regrouping or floorplanning to localize traffic.",
                        details={"big_clusters": big_clusters.tolist() if hasattr(big_clusters, 'tolist') else list(big_clusters)},
                    )
                )

        if not recomms:
            recomms.append(
                OptimizationRecommendation(priority="LOW", message="No major issues detected — design looks balanced.")
            )

        report.recommendations = recomms
        logger.info("generate_optimization_recommendations finished with %d recommendations", len(recomms))
        return recomms

    # -------------------------- orchestration --------------------------
    def run_all(self, n_subgraph: int = 2, n_clusters: int = 4) -> AdvancedAnalysisReport:
        """Pokreši sve glavne analize i skupi izveštaj.

        Ova metoda je korisna za brzinski izvšetak cele analize.
        """
        report = AdvancedAnalysisReport()
        report.subgraph_ns = self.subgraph_ns_analysis(n=n_subgraph)
        report.endpoint_offsets = self.endpoint_offset_analysis()
        report.congestion_evolution = self.congestion_evolution()
        report.signal_clusters = self.signal_cluster_analysis(n_clusters=n_clusters)
        report.routing_complexity = self.routing_complexity()
        report.recommendations = self.generate_optimization_recommendations(report)
        return report


# -------------------------- example usage --------------------------
if __name__ == "__main__":
    # brzi primer sa sintetičkim podacima
    G = nx.grid_2d_graph(10, 10)
    # re-label nodes to integers
    G = nx.convert_node_labels_to_integers(G)
    # add random positions
    for n in G.nodes():
        G.nodes[n]["pos"] = (float(n % 10), float(n // 10))

    # synth signals
    signals = []
    for i in range(50):
        s = {"name": f"sig_{i}", "endpoints": [i % 100, (i * 3) % 100], "path": [i % 100, (i * 3) % 100], "wire_length": float(i % 20)}
        signals.append(s)

    # synth routing data
    edge_cong = {}
    for e in G.edges():
        edge_cong[e] = float(np.random.rand())
    routing = {"edge_congestion": edge_cong, "congestion_history": [np.random.rand(10, 10) for _ in range(5)]}

    analyzer = AdvancedAnalyzer(G, signals, routing)
    report = analyzer.run_all()
    print(report)
