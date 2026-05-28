# ----------------------------------------------------------------------------------------------------------#
# Context-class to store analysis results in cache and distribute them to objective function and constraints
# ----------------------------------------------------------------------------------------------------------#
class EvalContext:  # Define a "helper" class to run the analysis only once per function evaluation
    def __init__(self, decode_func, analysis_func):  # constructor to create context object
        # stored callables
        self.decode = decode_func  # decode(x_idx) -> params dict
        self.results = analysis_func  # heavy_analysis(params) -> {"y","y_p","violations",...}

        # tiny single-entry memo cache
        self.last_key = None  # tuple of ints (candidate)
        self.last_data = None  # whatever heavy_analysis returns
        self.hits = 0  # hits = how often data was reused from cache
        self.misses = 0  # misses = how often data had to be executed

        # containers for active constraints and var names to pass them to logger
        self._c_names: list[str] = []  # constraint names to publish on self as c__<name>
        self._var_names: list[str] = []  # variable names to publish on self as var__<name> and idx__<name>
        # public attributes for logger to watch
        self.y = 0.0  # unpenalised (optional)
        self.y_p = 0.0  # penalised

    # --- declare stable attributes so IOH can bind watchers once and reuse them ---
    def ensure_constraints(self, names: list[str]):
        """Declare stable attributes for all active constraints so IOH can watch them."""
        self._c_names = list(names)
        for n in self._c_names:
            setattr(self, f"c__{n}", 0.0)

    def ensure_params(self, var_names: list[str]):
        """Declare stable attributes for decoded parameter values and their indices."""
        self._var_names = list(var_names)
        for n in self._var_names:
            # decoded value (float-like if possible)
            setattr(self, f"var__{n}", 0.0)
            # chosen catalogue index (always integer)
            setattr(self, f"idx__{n}", 0)

    def get(self, x_idx):
        key = tuple(int(k) for k in x_idx)
        if key == self.last_key:
            self.hits += 1
            rec = self.last_data
        else:
            self.misses += 1
            # decode -> analysis
            params = self.decode(x_idx)
            rec = self.results(params)
            self.last_key = key
            self.last_data = rec

        # publish fields for the logger (objective channels)
        self.y = float(rec.get("y", 0.0))
        self.y_p = float(rec.get("y_p", 0.0))

        # publish constraint channels (raw, non-negative violations expected)
        viol = rec.get("violations", {}) or {}
        for n in self._c_names:
            setattr(self, f"c__{n}", float(viol.get(n, 0.0)))

        # publish parameter channels
        # prefer the analysis-returned decoded map to avoid re-decoding drift
        pmap = rec.get("params")
        if pmap is None:
            # fallback to a fresh decode if analysis didn't return "params"
            try:
                pmap = self.decode(x_idx)
            except Exception:
                pmap = {}

        for i, n in enumerate(self._var_names):
            # decoded value (attempt float cast; if not numeric, leave previous numeric value)
            v = pmap.get(n)
            try:
                setattr(self, f"var__{n}", float(v))
            except (TypeError, ValueError):
                # keep previous numeric value to avoid breaking IOH numeric property
                pass
            # catalogue index from x_idx ordering
            try:
                setattr(self, f"idx__{n}", int(x_idx[i]))
            except Exception:
                # if dimension mismatch, keep previous
                pass

        return rec

    def reset(self):
        self.last_key = None
        self.last_data = None
        self.hits = self.misses = 0
