"use client";

import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import api from "@/lib/api";
import { UserRecord } from "@/lib/types";
import { CheckCircle, XCircle, Ban, RefreshCw } from "lucide-react";

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-yellow-50 text-yellow-700 border-yellow-200",
  rejected: "bg-red-50 text-red-600 border-red-200",
  disabled: "bg-zinc-100 text-zinc-500 border-zinc-200",
};

export default function AdminPage() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => { fetchUsers(); }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await api.get("/api/admin/users");
      setUsers(res.data);
    } catch {
      setUsers([
        { id: "1", email: "admin@tatva.in", role: "admin", status: "active", organization_id: null },
        { id: "2", email: "user@tatapower.com", role: "user", status: "pending", organization_id: null },
        { id: "3", email: "analyst@adani.com", role: "user", status: "pending", organization_id: null },
      ]);
      setNotice("Showing mock data. Start backend to manage real users.");
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (userId: string, action: "approve" | "reject" | "deactivate") => {
    setActionLoading(userId + action);
    try {
      await api.post(`/api/admin/${action}/${userId}`);
      await fetchUsers();
    } catch {
      setNotice("Action failed. Make sure backend is running.");
    } finally {
      setActionLoading(null);
    }
  };

  const pending = users.filter((u) => u.status === "pending").length;
  const active = users.filter((u) => u.status === "active").length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-zinc-900">User Management</h1>
          <p className="text-zinc-500 text-sm mt-0.5">Review and manage platform access requests</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-4 text-sm">
            <span className="flex items-center gap-1.5 text-zinc-500"><span className="w-2 h-2 rounded-full bg-yellow-400 inline-block" />{pending} pending</span>
            <span className="flex items-center gap-1.5 text-zinc-500"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />{active} active</span>
          </div>
          <Button variant="outline" size="sm" onClick={fetchUsers} className="h-8 text-xs border-zinc-200 gap-1.5">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>
      </div>

      {notice && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-4 py-2.5 rounded-lg">
          {notice}
        </div>
      )}

      <Card className="border-zinc-100 shadow-none overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-zinc-50 hover:bg-zinc-50 border-zinc-100">
              <TableHead className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Email</TableHead>
              <TableHead className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Role</TableHead>
              <TableHead className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Status</TableHead>
              <TableHead className="text-xs font-semibold text-zinc-400 uppercase tracking-wider text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-16 text-zinc-400 text-sm">Loading users...</TableCell>
              </TableRow>
            ) : users.map((user) => (
              <TableRow key={user.id} className="hover:bg-zinc-50/50 border-zinc-100">
                <TableCell className="font-medium text-zinc-800 text-sm">{user.email}</TableCell>
                <TableCell><span className="text-xs text-zinc-500 capitalize">{user.role}</span></TableCell>
                <TableCell>
                  <Badge variant="outline" className={`text-xs capitalize ${STATUS_STYLES[user.status] ?? ""}`}>
                    {user.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {user.status === "pending" && (
                      <>
                        <Button size="sm" variant="outline" className="h-7 text-xs text-emerald-600 border-emerald-200 hover:bg-emerald-50 gap-1" onClick={() => handleAction(user.id, "approve")} disabled={actionLoading === user.id + "approve"}>
                          <CheckCircle size={11} /> Approve
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 text-xs text-red-600 border-red-200 hover:bg-red-50 gap-1" onClick={() => handleAction(user.id, "reject")} disabled={actionLoading === user.id + "reject"}>
                          <XCircle size={11} /> Reject
                        </Button>
                      </>
                    )}
                    {user.status === "active" && user.role !== "admin" && (
                      <Button size="sm" variant="outline" className="h-7 text-xs text-zinc-500 border-zinc-200 hover:bg-zinc-50 gap-1" onClick={() => handleAction(user.id, "deactivate")} disabled={actionLoading === user.id + "deactivate"}>
                        <Ban size={11} /> Deactivate
                      </Button>
                    )}
                    {(user.role === "admin" || user.status === "rejected" || user.status === "disabled") && (
                      <span className="text-xs text-zinc-300">—</span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
