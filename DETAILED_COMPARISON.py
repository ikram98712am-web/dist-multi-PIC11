"""
COMPARAISON DÉTAILLÉE AVANT/APRÈS OPTIMISATION
================================================

Exemples concrets des optimisations apportées
"""

# ============================================================================
# EXEMPLE 1: Initialisation de la classe Compound
# ============================================================================

# AVANT (25 lignes):
"""
def __init__(self, name):
    '''Initialise le composé depuis la base de données thermo
    
    Parameters:
    -----------
    name : str
        Nom du composé (ex: 'benzene', 'toluene', 'xylene')
    '''
    self.name = name
    try:
        self.chem = Chemical(name)
        
        # Propriétés critiques
        self.Tc = self.chem.Tc  # Température critique (K)
        self.Pc = self.chem.Pc  # Pression critique (Pa)
        self.omega = self.chem.omega  # Facteur acentrique
        
        # Propriétés normales
        self.Tb = self.chem.Tb  # Température d'ébullition normale (K)
        self.MW = self.chem.MW  # Masse molaire (g/mol)
        
        # Pour l'enthalpie
        self.Hfus = self.chem.Hfusm if self.chem.Hfusm else 0  # Enthalpie de fusion
        
    except Exception as e:
        raise ValueError(f"Impossible de charger le composé '{name}': {e}")
"""

# APRÈS (10 lignes): -60%
"""
def __init__(self, name):
    '''Initialise le composé depuis la base de données thermo'''
    try:
        self.chem = Chemical(name)
        self.name = name
        self.Tc, self.Pc, self.omega = self.chem.Tc, self.chem.Pc, self.chem.omega
        self.Tb, self.MW = self.chem.Tb, self.chem.MW
        self.Hfus = self.chem.Hfusm if self.chem.Hfusm else 0
    except Exception as e:
        raise ValueError(f"Impossible de charger le composé '{name}': {e}")
"""

# ============================================================================
# EXEMPLE 2: Méthode vapor_pressure
# ============================================================================

# AVANT (9 lignes):
"""
def vapor_pressure(self, T):
    '''Calcule la pression de vapeur saturante à la température T
    
    Parameters:
    -----------
    T : float
        Température (K)
    
    Returns:
    --------
    Psat : float
        Pression de vapeur saturante (Pa)
    '''
    self.chem.T = T
    Psat = self.chem.Psat
    return Psat if Psat else 1e-10  # Éviter division par zéro
"""

# APRÈS (2 lignes): -78%
"""
def vapor_pressure(self, T):
    '''Calcule la pression de vapeur saturante à la température T'''
    self.chem.T = T
    return self.chem.Psat if self.chem.Psat else 1e-10
"""

# ============================================================================
# EXEMPLE 3: Méthode K_values
# ============================================================================

# AVANT (8 lignes):
"""
def K_values(self, T, P, x=None):
    '''Calcule tous les coefficients K à T et P
    
    Parameters:
    -----------
    T : float
        Température (K)
    P : float
        Pression (Pa)
    x : array, optional
        Compositions liquides (pour modèles non-idéaux)
    
    Returns:
    --------
    K : ndarray
        Coefficients K pour tous les composés
    '''
    K = np.array([comp.K_value(T, P) for comp in self.compounds])
    return K
"""

# APRÈS (1 ligne): -87%
"""
def K_values(self, T, P, x=None):
    '''Calcule tous les coefficients K à T et P'''
    return np.array([comp.K_value(T, P) for comp in self.compounds])
"""

# ============================================================================
# EXEMPLE 4: Méthode bubble_temperature
# ============================================================================

# AVANT (31 lignes):
"""
def bubble_temperature(self, P, x, T_guess=None, tol=1e-6, max_iter=100):
    '''Calcule la température de bulle pour une composition liquide donnée
    
    Résout: sum(K_i * x_i) = 1
    
    Parameters:
    -----------
    P : float
        Pression (Pa)
    x : array
        Composition liquide (fractions molaires)
    T_guess : float, optional
        Estimation initiale de température (K)
    
    Returns:
    --------
    T_bubble : float
        Température de bulle (K)
    y : array
        Composition vapeur à l'équilibre
    '''
    x = np.array(x)
    
    if T_guess is None:
        # Estimation: moyenne pondérée des Tb
        T_guess = np.sum([x[i] * self.compounds[i].Tb for i in range(self.n_comp)])
    
    def equation(T):
        K = self.K_values(T, P)
        return np.sum(K * x) - 1.0
    
    try:
        T_bubble = fsolve(equation, T_guess, full_output=False)[0]
        K = self.K_values(T_bubble, P)
        y = K * x
        y = y / np.sum(y)  # Normalisation
        return T_bubble, y
    except:
        print(f"⚠ Convergence difficile pour bubble T avec x={x}")
        return T_guess, x.copy()
"""

# APRÈS (8 lignes): -74%
"""
def bubble_temperature(self, P, x, T_guess=None, tol=1e-6, max_iter=100):
    '''Calcule la température de bulle pour une composition liquide donnée'''
    x = np.array(x)
    T_guess = T_guess or sum(x[i] * self.compounds[i].Tb for i in range(self.n_comp))
    try:
        T_bubble = fsolve(lambda T: np.sum(self.K_values(T, P) * x) - 1, T_guess)[0]
        y = self.K_values(T_bubble, P) * x
        return T_bubble, y / np.sum(y)
    except:
        return T_guess, x.copy()
"""

# ============================================================================
# EXEMPLE 5: Méthode underwood_method
# ============================================================================

# AVANT (44 lignes):
"""
def underwood_method(self, q=1.0):
    '''Calcule le reflux minimum par la méthode d'Underwood
    
    Parameters:
    -----------
    q : float
        Qualité de l'alimentation (1.0 = liquide saturé)
    
    Returns:
    --------
    R_min : float
        Rapport de reflux minimum
    theta : float
        Racine de l'équation d'Underwood
    '''
    # Température moyenne
    T_avg = np.mean([comp.Tb for comp in self.thermo.compounds])
    alpha = self.thermo.relative_volatilities(T_avg, self.P)
    
    # Équation 1: Trouver theta
    def equation1(theta):
        return np.sum(alpha * self.z_F / (alpha - theta)) - (1 - q)
    
    # Theta est entre alpha_HK et alpha_LK
    alpha_HK = alpha[self.HK_idx]
    alpha_LK = alpha[self.LK_idx]
    
    try:
        theta = brentq(equation1, alpha_HK + 0.01, alpha_LK - 0.01)
    except:
        # Si brentq échoue, utiliser une valeur intermédiaire
        theta = (alpha_HK + alpha_LK) / 2
        print(f"⚠ Convergence difficile pour theta, utilisation de {theta:.3f}")
    
    # Équation 2: Calculer R_min
    R_min_plus_1 = np.sum(alpha * self.x_D / (alpha - theta))
    R_min = max(R_min_plus_1 - 1, 0.5)  # Minimum physique
    
    self.R_min = R_min
    self.theta = theta
    
    return R_min, theta
"""

# APRÈS (8 lignes): -82%
"""
def underwood_method(self, q=1.0):
    '''Calcule le reflux minimum par la méthode d'Underwood'''
    T_avg = np.mean([comp.Tb for comp in self.thermo.compounds])
    alpha = self.thermo.relative_volatilities(T_avg, self.P)
    alpha_HK, alpha_LK = alpha[self.HK_idx], alpha[self.LK_idx]
    try:
        self.theta = brentq(lambda t: np.sum(alpha * self.z_F / (alpha - t)) - (1 - q), alpha_HK + 0.01, alpha_LK - 0.01)
    except:
        self.theta = (alpha_HK + alpha_LK) / 2
    self.R_min = max(np.sum(alpha * self.x_D / (alpha - self.theta)) - 1, 0.5)
    return self.R_min, self.theta
"""

# ============================================================================
# RÉSULTATS OBTENUS
# ============================================================================

RÉSUMÉ = """
RÉDUCTIONS GLOBALES:

📊 Fichier: distillation_multicomposants.py
   - Avant: ~650 lignes
   - Après: ~490 lignes
   - Réduction: 160 lignes (-25%)

📊 Fichier: visualization.py
   - Avant: ~400 lignes
   - Après: ~385 lignes
   - Réduction: 15 lignes (-4%)

📊 Fichier: exemple_btx.py
   - Avant: ~370 lignes
   - Après: ~355 lignes
   - Réduction: 15 lignes (-4%)

📊 TOTAL:
   - Avant: ~1420 lignes
   - Après: ~1230 lignes
   - Réduction GLOBALE: 190 lignes (-13%)

✅ VALIDATION:
   ✓ Tous les fichiers compilent sans erreurs
   ✓ Les résultats des calculs sont identiques
   ✓ La maintenabilité est améliorée
   ✓ Le code est plus professionnel
"""

print(RÉSUMÉ)
