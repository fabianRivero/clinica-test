/**
 * Almacena el branchId activo seleccionado por el admin principal.
 * Las funciones API lo leen automáticamente para inyectar el query param.
 * El BranchProvider lo actualiza cada vez que cambia la sucursal activa.
 */
let _activeBranchId: number | null = null

export function setActiveBranchId(branchId: number | null) {
  _activeBranchId = branchId
}

export function getActiveBranchId(): number | null {
  return _activeBranchId
}
