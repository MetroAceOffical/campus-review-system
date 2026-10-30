import { request } from './http'
export const roles: Record<string,string> = { MEMBER:'创作者',REVIEWER:'审核员',ADMIN:'管理员' }
export interface Department { id: string; name: string; enabled: boolean; memberCount?: number; manuscriptCount?: number }
export interface Account { id: string; username: string; displayName: string; role: string; enabled: boolean; organizations: Department[] }
export interface UserInput { username?: string; displayName: string; password?: string; role: string; enabled: boolean; organizationIds: string[] }
export interface Task { id: string; kind: string; action: string; status: string; target: string; createdAt: string; finishedAt: string | null }
export interface AuditLog { id: string; actor: string; objectType: string; objectId: string; operation: string; details: string; createdAt: string }
interface Page<T> { items:T[];total:number }
const query=(fields:Record<string,string|number>)=>new URLSearchParams(Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,String(v)])))
export const users=(page:number,q:string,role:string,enabled:string,pageSize=20)=>request<Page<Account>>(`/api/system/users?${query({page,q,role,enabled,pageSize})}`)
export const saveUser=(id:string|undefined,value:UserInput)=>request(`/api/system/users${id?'/'+id:''}`,{method:id?'PUT':'POST',body:JSON.stringify(value)})
export const organizations=(page:number,q:string,pageSize=20)=>request<Page<Department>>(`/api/system/organizations?${query({page,q,pageSize})}`)
export const organizationOptions=()=>request<Department[]>('/api/system/organization-options')
export const saveOrganization=(id:string|undefined,value:{name:string;enabled:boolean})=>request(`/api/system/organizations${id?'/'+id:''}`,{method:id?'PUT':'POST',body:JSON.stringify(value)})
export const logs=(page:number,q:string,pageSize=20)=>request<Page<AuditLog>>(`/api/system/logs?${query({page,q,pageSize})}`)
export const tasks=(page:number,q:string,status:string,pageSize=20)=>request<Page<Task>>(`/api/system/tasks?${query({page,q,status,pageSize})}`)
export interface Diagnostics { java:string;database:string;detector:{ready:boolean;busy:boolean};ocr:{ready:boolean;busy:boolean} }
export const diagnostics=()=>request<Diagnostics>('/api/system/diagnostics')
