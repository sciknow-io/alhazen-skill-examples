import Link from "next/link";
import { installedSkills } from "../../skills.config";

export default function HubPage() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-10">
          <h1 className="text-3xl font-bold text-foreground mb-2">
            Alhazen Skill Examples
          </h1>
          <p className="text-muted-foreground">
            Demo dashboard for the Alhazen knowledge notebook framework
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {installedSkills.map((skill) => (
            <Link key={skill.path} href={skill.path}>
              <div className="rounded-lg border border-border bg-card p-6 hover:bg-accent/10 transition-colors cursor-pointer">
                <div className="flex items-start justify-between mb-3">
                  <h2 className="text-lg font-semibold text-foreground">
                    {skill.name}
                  </h2>
                  <span className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary font-medium">
                    {skill.category}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {skill.description}
                </p>
                <div className="mt-4 text-xs text-primary font-medium">
                  Open dashboard →
                </div>
              </div>
            </Link>
          ))}
        </div>

        <div className="mt-12 pt-8 border-t border-border">
          <p className="text-xs text-muted-foreground">
            Skills are defined in <code className="font-mono">skills/</code> and
            assembled into this app via <code className="font-mono">make demo-sync</code>.
            See the{" "}
            <a
              href="https://github.com/sciknow-io/alhazen-skill-examples"
              className="text-primary underline underline-offset-2 hover:text-primary/80"
            >
              README
            </a>{" "}
            for details.
          </p>
        </div>
      </div>
    </main>
  );
}
