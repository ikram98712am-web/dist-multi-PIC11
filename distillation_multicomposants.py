"""
Distillation de Mélanges Multicomposants
==========================================
Modélisation et simulation complète avec méthodes simplifiées et rigoureuses

Auteur: Prof. BAKHER Zine Elabidine
Cours: Modélisation et Simulation des Procédés - PIC
Université uh1
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import fsolve, brentq, minimize
from scipy.linalg import solve_banded
from thermo.chemical import Chemical
from thermo import ChemicalConstantsPackage, PRMIX, CEOSLiquid, CEOSGas
import warnings
warnings.filterwarnings('ignore')

# Pour visualisations interactives
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠ Plotly non disponible. Installation: pip install plotly")
    print("  Les visualisations interactives ne seront pas disponibles.")

class Compound:
    """
    Représente un composé chimique avec ses propriétés thermodynamiques
    """
    
    def __init__(self, name):
        """Initialise le composé depuis la base de données thermo"""
        try:
            self.chem = Chemical(name)
            self.name = name
            self.Tc, self.Pc, self.omega = self.chem.Tc, self.chem.Pc, self.chem.omega
            self.Tb, self.MW = self.chem.Tb, self.chem.MW
            self.Hfus = self.chem.Hfusm if self.chem.Hfusm else 0
        except Exception as e:
            raise ValueError(f"Impossible de charger le composé '{name}': {e}")
    
    def vapor_pressure(self, T):
        """Calcule la pression de vapeur saturante à la température T"""
        self.chem.T = T
        return self.chem.Psat if self.chem.Psat else 1e-10
    
    def K_value(self, T, P):
        """Calcule le coefficient de partage K = Psat(T) / P"""
        return self.vapor_pressure(T) / P
    
    def enthalpy_liquid(self, T, T_ref=298.15):
        """Calcule l'enthalpie du liquide à T par rapport à T_ref"""
        self.chem.T = T
        try:
            return self.chem.Cplm * (T - T_ref)
        except:
            return 4.18 * self.MW * (T - T_ref)
    
    def enthalpy_vapor(self, T, T_ref=298.15):
        """Calcule l'enthalpie de la vapeur à T par rapport à T_ref"""
        self.chem.T = T
        return self.enthalpy_liquid(T, T_ref) + (self.chem.Hvap if self.chem.Hvap else 40000)
    
    def __repr__(self):
        return f"Compound(name='{self.name}', Tb={self.Tb-273.15:.1f}°C, MW={self.MW:.2f})"


class ThermodynamicPackage:
    """
    Package thermodynamique pour calculs d'équilibre et propriétés de mélanges
    """
    
    def __init__(self, compounds):
        """
        Parameters:
        -----------
        compounds : list of Compound objects
            Liste des composés du mélange
        """
        self.compounds = compounds
        self.n_comp = len(compounds)
        self.compound_names = [c.name for c in compounds]
        
    def K_values(self, T, P, x=None):
        """Calcule tous les coefficients K à T et P"""
        return np.array([comp.K_value(T, P) for comp in self.compounds])
    
    def relative_volatilities(self, T, P, ref_index=-1):
        """Calcule les volatilités relatives par rapport au composé de référence"""
        K = self.K_values(T, P)
        return K / K[ref_index]
    
    def bubble_temperature(self, P, x, T_guess=None, tol=1e-6, max_iter=100):
        """Calcule la température de bulle pour une composition liquide donnée"""
        x = np.array(x)
        T_guess = T_guess or sum(x[i] * self.compounds[i].Tb for i in range(self.n_comp))
        try:
            T_bubble = fsolve(lambda T: np.sum(self.K_values(T, P) * x) - 1, T_guess)[0]
            y = self.K_values(T_bubble, P) * x
            return T_bubble, y / np.sum(y)
        except:
            return T_guess, x.copy()
    
    def dew_temperature(self, P, y, T_guess=None, tol=1e-6, max_iter=100):
        """Calcule la température de rosée pour une composition vapeur donnée"""
        y = np.array(y)
        T_guess = T_guess or sum(y[i] * self.compounds[i].Tb for i in range(self.n_comp))
        try:
            T_dew = fsolve(lambda T: np.sum(y / self.K_values(T, P)) - 1, T_guess)[0]
            x = y / self.K_values(T_dew, P)
            return T_dew, x / np.sum(x)
        except:
            return T_guess, y.copy()
    
    def mixture_enthalpy_liquid(self, T, x, T_ref=298.15):
        """Calcule l'enthalpie du mélange liquide"""
        return sum(x[i] * self.compounds[i].enthalpy_liquid(T, T_ref) for i in range(self.n_comp))
    
    def mixture_enthalpy_vapor(self, T, y, T_ref=298.15):
        """Calcule l'enthalpie du mélange vapeur"""
        return sum(y[i] * self.compounds[i].enthalpy_vapor(T, T_ref) for i in range(self.n_comp))
    
    def print_properties(self, T, P):
        """
        Affiche les propriétés à T et P
        """
        print(f"\n{'PROPRIETES A T={T-273.15:.1f}C, P={P/1e5:.3f} bar':-^80}")
        print(f"{'Compose':<15} {'Tb (C)':<12} {'Psat (kPa)':<15} {'K':<12} {'alpha':<12}")
        print("-" * 80)
        
        K = self.K_values(T, P)
        alpha = self.relative_volatilities(T, P)
        
        for i, comp in enumerate(self.compounds):
            Psat = comp.vapor_pressure(T)
            print(f"{comp.name:<15} {comp.Tb-273.15:<12.2f} {Psat/1000:<15.2f} "
                  f"{K[i]:<12.4f} {alpha[i]:<12.4f}")
        print("-" * 80)


class ShortcutDistillation:
    """
    Méthodes simplifiées de dimensionnement (Fenske, Underwood, Gilliland, Kirkbride)
    """
    
    def __init__(self, thermo_package, F, z_F, P=101325):
        """
        Parameters:
        -----------
        thermo_package : ThermodynamicPackage
            Package thermodynamique
        F : float
            Débit d'alimentation (kmol/h)
        z_F : array
            Composition de l'alimentation (fractions molaires)
        P : float
            Pression de la colonne (Pa)
        """
        self.thermo = thermo_package
        self.F = F
        self.z_F = np.array(z_F)
        self.P = P
        self.n_comp = len(z_F)
        
        # Identifier les composés clés
        self._identify_key_components()
        
    def _identify_key_components(self):
        """Identifie les composés clés (léger et lourd)"""
        T_avg = np.mean([comp.Tb for comp in self.thermo.compounds])
        alpha = self.thermo.relative_volatilities(T_avg, self.P)
        sorted_indices = np.argsort(alpha)[::-1]
        threshold = 0.01
        self.LK_idx = next(idx for idx in sorted_indices if self.z_F[idx] > threshold)
        self.HK_idx = next(idx for idx in sorted_indices[::-1] if self.z_F[idx] > threshold)
        print(f"\n[OK] Cle leger (LK): {self.thermo.compound_names[self.LK_idx]}  | Cle lourd (HK): {self.thermo.compound_names[self.HK_idx]}")
    
    def material_balance(self, recovery_LK_D=0.95, recovery_HK_B=0.95):
        """
        Calcule les bilans matières globaux
        
        Parameters:
        -----------
        recovery_LK_D : float
            Récupération du clé léger dans le distillat (fraction)
        recovery_HK_B : float
            Récupération du clé lourd dans le résidu (fraction)
        
        Returns:
        --------
        D : float
            Débit de distillat (kmol/h)
        B : float
            Débit de résidu (kmol/h)
        x_D : array
            Composition du distillat
        x_B : array
            Composition du résidu
        """
        # Débits des clés
        LK_in_feed = self.F * self.z_F[self.LK_idx]
        HK_in_feed = self.F * self.z_F[self.HK_idx]
        
        # Distribution selon les récupérations
        LK_in_D = recovery_LK_D * LK_in_feed
        LK_in_B = LK_in_feed - LK_in_D
        
        HK_in_B = recovery_HK_B * HK_in_feed
        HK_in_D = HK_in_feed - HK_in_B
        
        # Initialisation des compositions
        d = np.zeros(self.n_comp)  # Débits dans distillat
        b = np.zeros(self.n_comp)  # Débits dans résidu
        
        d[self.LK_idx] = LK_in_D
        d[self.HK_idx] = HK_in_D
        b[self.LK_idx] = LK_in_B
        b[self.HK_idx] = HK_in_B
        
        # Distribution des composés non-clés
        T_avg = np.mean([comp.Tb for comp in self.thermo.compounds])
        alpha = self.thermo.relative_volatilities(T_avg, self.P)
        for i in range(self.n_comp):
            if i != self.LK_idx and i != self.HK_idx:
                if alpha[i] > alpha[self.LK_idx]:
                    d[i] = self.F * self.z_F[i]
                elif alpha[i] < alpha[self.HK_idx]:
                    b[i] = self.F * self.z_F[i]
                else:
                    ratio = (alpha[i] - alpha[self.HK_idx]) / (alpha[self.LK_idx] - alpha[self.HK_idx])
                    d[i], b[i] = ratio * self.F * self.z_F[i], (1 - ratio) * self.F * self.z_F[i]
        
        D = np.sum(d)
        B = np.sum(b)
        
        x_D = d / D
        x_B = b / B
        
        self.D = D
        self.B = B
        self.x_D = x_D
        self.x_B = x_B
        
        return D, B, x_D, x_B
    
    def fenske_equation(self):
        """Calcule le nombre minimum de plateaux (reflux total)"""
        T_avg = (self.thermo.compounds[self.LK_idx].Tb + self.thermo.compounds[self.HK_idx].Tb) / 2
        alpha = self.thermo.relative_volatilities(T_avg, self.P)
        self.alpha_avg = alpha[self.LK_idx] / alpha[self.HK_idx]
        ratio_D = self.x_D[self.LK_idx] / self.x_D[self.HK_idx]
        ratio_B = self.x_B[self.LK_idx] / self.x_B[self.HK_idx]
        self.N_min = np.log(ratio_D / ratio_B) / np.log(self.alpha_avg)
        return self.N_min, self.alpha_avg
    
    def underwood_method(self, q=1.0):
        """Calcule le reflux minimum par la méthode d'Underwood"""
        T_avg = np.mean([comp.Tb for comp in self.thermo.compounds])
        alpha = self.thermo.relative_volatilities(T_avg, self.P)
        alpha_HK, alpha_LK = alpha[self.HK_idx], alpha[self.LK_idx]
        try:
            self.theta = brentq(lambda t: np.sum(alpha * self.z_F / (alpha - t)) - (1 - q), alpha_HK + 0.01, alpha_LK - 0.01)
        except:
            self.theta = (alpha_HK + alpha_LK) / 2
        self.R_min = max(np.sum(alpha * self.x_D / (alpha - self.theta)) - 1, 0.5)
        return self.R_min, self.theta
    
    def gilliland_correlation(self, R):
        """Calcule le nombre de plateaux avec la corrélation de Gilliland"""
        X = (R - self.R_min) / (R + 1)
        Y = 1 - np.exp((1 + 54.4*X) * (X - 1) / ((11 + 117.2*X) * np.sqrt(X + 1e-10)))
        return self.N_min + Y / (1 - Y + 1e-10)
    
    def kirkbride_equation(self, N_total):
        """Détermine la position du plateau d'alimentation"""
        ratio_term = (self.B / self.D) * (self.z_F[self.HK_idx] / self.z_F[self.LK_idx]) * (self.x_B[self.LK_idx] / self.x_D[self.HK_idx])**2
        N_R_over_N_S = np.exp(0.206 * np.log(ratio_term + 1e-10))
        N_S = N_total / (1 + N_R_over_N_S)
        N_R = N_total - N_S
        return int(np.ceil(N_R)), int(np.floor(N_S)), int(np.ceil(N_R)) + 1
    
    def complete_shortcut_design(self, recovery_LK_D=0.95, recovery_HK_B=0.95,
                                 R_factor=1.3, q=1.0, efficiency=0.70):
        """
        Dimensionnement complet par méthodes simplifiées
        
        Parameters:
        -----------
        recovery_LK_D : float
            Récupération clé léger dans distillat
        recovery_HK_B : float
            Récupération clé lourd dans résidu
        R_factor : float
            Facteur multiplicatif pour reflux (R = R_factor * R_min)
        q : float
            Qualité alimentation
        efficiency : float
            Efficacité des plateaux
        
        Returns:
        --------
        results : dict
            Dictionnaire avec tous les résultats
        """
        print("\n" + "=" * 80)
        print("DIMENSIONNEMENT PAR METHODES SIMPLIFIEES")
        print("=" * 80)
        
        # 1. Bilans matières
        print("\n1. BILANS MATIERES GLOBAUX")
        D, B, x_D, x_B = self.material_balance(recovery_LK_D, recovery_HK_B)
        
        print(f"   Debit distillat: D = {D:.2f} kmol/h")
        print(f"   Debit residu: B = {B:.2f} kmol/h")
        
        # 2. Fenske
        print("\n2. EQUATION DE FENSKE (reflux total)")
        N_min, alpha_avg = self.fenske_equation()
        print(f"   N_min = {N_min:.2f} plateaux theoriques")
        print(f"   α_avg(LK/HK) = {alpha_avg:.3f}")
        
        # 3. Underwood
        print("\n3. METHODE D'UNDERWOOD (reflux minimum)")
        R_min, theta = self.underwood_method(q)
        print(f"   R_min = {R_min:.3f}")
        print(f"   theta = {theta:.3f}")
        
        # 4. Gilliland
        print("\n4. CORRELATION DE GILLILAND")
        R = R_factor * R_min
        N_theoretical = self.gilliland_correlation(R)
        print(f"   R operatoire = {R:.3f} ({R_factor}x R_min)")
        print(f"   N theorique = {N_theoretical:.2f} plateaux")
        
        # 5. Plateaux réels
        N_real = int(np.ceil(N_theoretical / efficiency))
        print(f"   Efficacite = {efficiency*100:.1f}%")
        print(f"   N reel = {N_real} plateaux")
        
        # 6. Kirkbride
        print("\n5. EQUATION DE KIRKBRIDE (position alimentation)")
        N_R, N_S, feed_stage = self.kirkbride_equation(N_real)
        print(f"   Plateaux rectification: {N_R}")
        print(f"   Plateaux epuisement: {N_S}")
        print(f"   Plateau d'alimentation: {feed_stage}")
        
        # 7. Débits internes
        print("\n6. DEBITS INTERNES")
        L = R * D
        V = L + D
        L_prime = L + self.F * q  # Hypothèse: q fraction liquide
        V_prime = V
        
        print(f"   Liquide rectification: L = {L:.2f} kmol/h")
        print(f"   Vapeur rectification: V = {V:.2f} kmol/h")
        print(f"   Liquide epuisement: L' = {L_prime:.2f} kmol/h")
        print(f"   Vapeur epuisement: V' = {V_prime:.2f} kmol/h")
        
        print("\n" + "=" * 80)
        
        results = {
            'D': D,
            'B': B,
            'x_D': x_D,
            'x_B': x_B,
            'N_min': N_min,
            'alpha_avg': alpha_avg,
            'R_min': R_min,
            'theta': theta,
            'R': R,
            'N_theoretical': N_theoretical,
            'N_real': N_real,
            'efficiency': efficiency,
            'N_R': N_R,
            'N_S': N_S,
            'feed_stage': feed_stage,
            'L': L,
            'V': V,
            'L_prime': L_prime,
            'V_prime': V_prime,
            'recovery_LK_D': recovery_LK_D,
            'recovery_HK_B': recovery_HK_B
        }
        
        return results

# Suite dans le prochain fichier...