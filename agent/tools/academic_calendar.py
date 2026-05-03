from datetime import datetime
from typing import Tuple

def get_current_academic_period(current_date: datetime = None) -> Tuple[int, str]:
    """
    Returns the current semester and tahun_ajaran based on the ITB academic calendar policy.
    
    ITB Policy:
    - Semester 1 (Ganjil): August to December/January.
    - Semester 2 (Genap): January/February to May/June.
    - Semester 3 (Pendek/SP): June to July (in between).
    
    Args:
        current_date: The date to evaluate. Defaults to datetime.now().
        
    Returns:
        tuple[int, str]: (semester_number, tahun_ajaran)
        e.g., (1, "2024/2025")
    """
    if current_date is None:
        current_date = datetime.now()
        
    month = current_date.month
    year = current_date.year
    
    if month >= 8:
        # August - December: Semester 1 (Ganjil) of the new academic year
        semester = 1
        tahun_ajaran = f"{year}/{year+1}"
    elif month == 1:
        # January: Still considered Semester 1 (Ganjil) of the previous year's start
        semester = 1
        tahun_ajaran = f"{year-1}/{year}"
    elif 2 <= month <= 5:
        # February - May: Semester 2 (Genap)
        semester = 2
        tahun_ajaran = f"{year-1}/{year}"
    else:
        # June - July: Semester 3 (Pendek / SP)
        semester = 3
        tahun_ajaran = f"{year-1}/{year}"
        
    return semester, tahun_ajaran
