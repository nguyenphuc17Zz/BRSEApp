import React, { useState, useEffect } from 'react';
import { 
  FolderKanban, 
  Plus, 
  Trash2, 
  ListChecks, 
  Check, 
  Globe, 
  Layers,
  ArrowRight
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, ProjectInstruction } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { Skeleton } from '../components/skeletons/Skeleton';

interface ProjectsPageProps {
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project | null) => void;
  refreshProjects: () => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  projects,
  activeProject,
  setActiveProject,
  refreshProjects
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [selectedProject, setSelectedProject] = useState<Project | null>(activeProject || projects[0] || null);
  const [instructions, setInstructions] = useState<ProjectInstruction[]>([]);
  const [newRule, setNewRule] = useState('');
  
  // Create Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [clientName, setClientName] = useState('');
  const [description, setDescription] = useState('');
  const [ruleInput, setRuleInput] = useState('');

  useEffect(() => {
    if (selectedProject) {
      loadInstructions(selectedProject.id);
    }
  }, [selectedProject]);

  const loadInstructions = async (projectId: string) => {
    try {
      const list = await apiClient.getProjectInstructions(projectId);
      setInstructions(list);
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !code.trim()) return;

    try {
      const initialRules = ruleInput.split('\n').map(r => r.trim()).filter(Boolean);
      const created = await apiClient.createProject({
        name,
        code: code.toUpperCase(),
        client_name: clientName,
        description,
        instructions: initialRules
      });
      setShowCreateModal(false);
      setName('');
      setCode('');
      setClientName('');
      setDescription('');
      setRuleInput('');
      refreshProjects();
      setSelectedProject(created);
      setActiveProject(created);
      toast.success(`Đã tạo dự án ${created.name} thành công`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err.message, 'Failed to create project');
    }
  };

  const handleAddInstruction = async () => {
    if (!selectedProject || !newRule.trim()) return;
    try {
      await apiClient.addProjectInstruction(selectedProject.id, newRule.trim());
      setNewRule('');
      loadInstructions(selectedProject.id);
      refreshProjects();
      toast.success('Đã thêm hướng dẫn dự án');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to add rule');
    }
  };

  const handleDeleteInstruction = async (id: string) => {
    if (!selectedProject) return;
    try {
      await apiClient.deleteProjectInstruction(selectedProject.id, id);
      loadInstructions(selectedProject.id);
      refreshProjects();
      toast.success('Đã xóa hướng dẫn dự án');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete rule');
    }
  };

  const handleDeleteProject = async (id: string) => {
    const ok = await confirm({
      title: 'Xóa dự án',
      message: 'Bạn có chắc chắn muốn xóa dự án này? Toàn bộ hướng dẫn, thuật ngữ và bộ nhớ dịch liên quan sẽ bị xóa vĩnh viễn.',
      isDestructive: true,
      confirmText: 'Xóa dự án'
    });
    if (!ok) return;

    try {
      await apiClient.deleteProject(id);
      refreshProjects();
      setSelectedProject(null);
      if (activeProject?.id === id) setActiveProject(null);
      toast.success('Đã xóa dự án thành công');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete project');
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-950 p-6 space-y-4">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <FolderKanban className="w-5 h-5 text-sky-400" />
            Project Workspaces
          </h2>
          <p className="text-xs text-slate-400">
            Configure project-specific translation behaviors, custom rules, and client terminology.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/20"
        >
          <Plus className="w-3.5 h-3.5" />
          New Project
        </button>
      </div>

      {/* Main Grid: Projects List + Selected Project Workspace */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden">
        {/* Project List */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 flex flex-col space-y-3 overflow-y-auto">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            All Projects ({projects.length})
          </h3>

          <div className="space-y-2 flex-1">
            {projects.length === 0 ? (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full rounded-lg" />
                <Skeleton className="h-20 w-full rounded-lg" />
                <Skeleton className="h-20 w-full rounded-lg" />
              </div>
            ) : (
              projects.map((p) => {
                const isSelected = selectedProject?.id === p.id;
                const isActive = activeProject?.id === p.id;
                return (
                  <div
                    key={p.id}
                    onClick={() => setSelectedProject(p)}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-sky-500 bg-slate-850 shadow-md'
                        : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-white">{p.name}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        {p.code}
                      </span>
                    </div>

                    <div className="text-[11px] text-slate-400 truncate">
                      Client: {p.client_name || 'Standard Client'}
                    </div>

                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/80 text-[10px] text-slate-500">
                      <span>{p.instructions_count} rules • {p.glossary_count} terms</span>
                      {isActive ? (
                        <span className="text-emerald-400 font-semibold flex items-center gap-1">
                          <Check className="w-3 h-3" /> Active
                        </span>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveProject(p);
                          }}
                          className="text-sky-400 hover:text-sky-300"
                        >
                          Set Active
                        </button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Selected Project Details & Rule Management */}
        <div className="lg:col-span-2 p-5 rounded-xl border border-slate-800 bg-slate-900/50 flex flex-col overflow-hidden space-y-4">
          {selectedProject ? (
            <>
              {/* Project Header */}
              <div className="flex items-start justify-between border-b border-slate-800 pb-4">
                <div>
                  <div className="flex items-center gap-2.5">
                    <h3 className="text-lg font-bold text-white">{selectedProject.name}</h3>
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/50">
                      {selectedProject.code}
                    </span>
                    {activeProject?.id === selectedProject.id ? (
                      <span className="text-xs px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/50 flex items-center gap-1">
                        <Check className="w-3 h-3" /> Active in Translator
                      </span>
                    ) : (
                      <button
                        onClick={() => setActiveProject(selectedProject)}
                        className="text-xs px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                      >
                        Make Active
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    {selectedProject.description || 'No description provided.'}
                  </p>
                  <div className="flex items-center gap-4 text-xs text-slate-500 mt-2">
                    <span>Client: <strong className="text-slate-300">{selectedProject.client_name || 'N/A'}</strong></span>
                    <span>Default Style: <strong className="text-slate-300">{selectedProject.default_style}</strong></span>
                  </div>
                </div>

                <button
                  onClick={() => handleDeleteProject(selectedProject.id)}
                  className="p-1.5 rounded text-slate-500 hover:text-rose-400 transition-colors"
                  title="Delete Project"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {/* Instructions Section */}
              <div className="flex-1 flex flex-col overflow-hidden space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <ListChecks className="w-4 h-4 text-sky-400" />
                    Mandatory Translation Instructions ({instructions.length})
                  </h4>
                  <span className="text-[11px] text-slate-500">
                    Automatically injected into AI prompts for this project
                  </span>
                </div>

                {/* Add Rule Input */}
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={newRule}
                    onChange={(e) => setNewRule(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddInstruction(); }}
                    placeholder="e.g. Always translate 障害 as 'sự cố', never use 'lỗi'..."
                    className="flex-1 bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-sky-500"
                  />
                  <button
                    onClick={handleAddInstruction}
                    disabled={!newRule.trim()}
                    className="px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium disabled:opacity-50"
                  >
                    Add Rule
                  </button>
                </div>

                {/* Rule List */}
                <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                  {instructions.map((inst, index) => (
                    <div
                      key={inst.id}
                      className="p-3 rounded-lg border border-slate-800 bg-slate-850 flex items-center justify-between text-xs text-slate-200"
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono text-slate-500 text-[11px]">#{index + 1}</span>
                        <span>{inst.rule_text}</span>
                      </div>
                      <button
                        onClick={() => handleDeleteInstruction(inst.id)}
                        className="text-slate-500 hover:text-rose-400 p-1 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}

                  {instructions.length === 0 && (
                    <div className="text-xs text-slate-500 text-center py-8">
                      No custom instructions added yet. Add rules above to guide the AI.
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-500 text-xs">
              Select or create a project to view instructions.
            </div>
          )}
        </div>
      </div>

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleCreate}
            className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white">Create New Project Workspace</h3>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-300 block mb-1">Project Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. ABC Banking System"
                  className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Project Code (Unique Identifier) *</label>
                <input
                  type="text"
                  required
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="e.g. ABC-BANK"
                  className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 font-mono uppercase focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Client Name</label>
                <input
                  type="text"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  placeholder="e.g. Japanese Financial Corp"
                  className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Overview of the system, tech stack, and scope..."
                  className="w-full h-16 bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-sky-500 resize-none"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Initial Project Rules (one per line)</label>
                <textarea
                  value={ruleInput}
                  onChange={(e) => setRuleInput(e.target.value)}
                  placeholder="e.g. Always use 'người dùng' instead of 'user'&#10;Do not translate endpoint names"
                  className="w-full h-20 bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-sky-500 resize-none font-mono text-[11px]"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
              >
                Create Project
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
