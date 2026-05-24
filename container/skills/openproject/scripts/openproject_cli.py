#!/usr/bin/env python3
"""OpenProject CLI wrapper for NanoClaw integration.

This script acts as a thin HTTP client to the OpenProject MCP Server,
providing command-line access to OpenProject operations for NanoClaw.

Usage:
    python openproject_cli.py <command> [arguments]

Environment:
    OPENPROJECT_MCP_URL: URL to MCP server (default: http://localhost:8085)
"""
import argparse
import json
import sys
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import httpx


class OpenProjectCLI:
    """CLI wrapper for OpenProject MCP server operations."""

    def __init__(self, mcp_url: Optional[str] = None):
        """Initialize the CLI with MCP server URL.

        Args:
            mcp_url: Base URL of the MCP server. If not provided, uses
                    OPENPROJECT_MCP_URL environment variable or default.
        """
        self.mcp_url = mcp_url or os.getenv(
            "OPENPROJECT_MCP_URL",
            "http://localhost:8085"
        ).rstrip("/")
        self.timeout = 30.0

    async def _call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Call a tool on the MCP server via HTTP.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Arguments to pass to the tool

        Returns:
            Response from the MCP server

        Raises:
            httpx.HTTPError: If the HTTP request fails
            json.JSONDecodeError: If the response is not valid JSON
        """
        url = f"{self.mcp_url}/tools/{tool_name}"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=kwargs, headers=headers)
            response.raise_for_status()
            return response.json()

    def _call_tool_sync(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for _call_tool using httpx.post.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Arguments to pass to the tool

        Returns:
            Response from the MCP server
        """
        url = f"{self.mcp_url}/tools/{tool_name}"
        headers = {"Content-Type": "application/json"}

        response = httpx.post(url, json=kwargs, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ====== Project Management Commands ======

    def create_project(
        self,
        name: str,
        description: str = "",
        public: bool = False
    ) -> Dict[str, Any]:
        """Create a new project.

        Args:
            name: Project name
            description: Project description
            public: Whether the project is public

        Returns:
            Result with project_id and details
        """
        return self._call_tool_sync(
            "create_project",
            name=name,
            description=description
        )

    def list_projects(self) -> Dict[str, Any]:
        """List all active projects.

        Returns:
            List of projects with IDs and names
        """
        return self._call_tool_sync("get_projects")

    def get_project_summary(self, project_id: int) -> Dict[str, Any]:
        """Get overview of a project.

        Args:
            project_id: ID of the project

        Returns:
            Project summary including task counts and status breakdown
        """
        return self._call_tool_sync(
            "get_project_summary",
            project_id=project_id
        )

    # ====== Work Package Commands ======

    def create_task(
        self,
        project_id: int,
        subject: str,
        description: str = "",
        start_date: Optional[str] = None,
        due_date: Optional[str] = None,
        assignee_email: Optional[str] = None,
        estimated_hours: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create a work package (task) in a project.

        Args:
            project_id: Target project ID
            subject: Task title
            description: Detailed description
            start_date: Start date in YYYY-MM-DD format
            due_date: Due date in YYYY-MM-DD format
            assignee_email: Email of assigned user
            estimated_hours: Time estimate in hours

        Returns:
            Result with work_package_id and details
        """
        result = self._call_tool_sync(
            "create_work_package",
            project_id=project_id,
            subject=subject,
            description=description,
            start_date=start_date,
            due_date=due_date,
            estimated_hours=estimated_hours
        )

        # If assignee email provided, assign after creation
        if assignee_email and result.get("success"):
            wp_id = result.get("work_package", {}).get("id")
            self.assign_task_by_email(wp_id, assignee_email)

        return result

    def get_tasks_by_date(
        self,
        date_range: str,
        projects: str = "all",
        status: str = "open"
    ) -> Dict[str, Any]:
        """Query work packages across projects by due date range.

        THE KILLER FEATURE for NanoClaw daily agenda queries.

        Args:
            date_range: Date range string
                - "today" → today only
                - "today to +2" → today through 2 days from now
                - "YYYY-MM-DD to YYYY-MM-DD" → explicit range
            projects: Project scope ("all" or comma-separated IDs)
            status: Status filter ("open", "closed", "all")

        Returns:
            Tasks grouped by project within the date range
        """
        # Parse date range
        from utils.date_helpers import normalize_date_range

        try:
            start_date, end_date = normalize_date_range(date_range)
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid date range: {e}"
            }

        # Parse project IDs if specified
        project_ids = None
        if projects != "all":
            try:
                project_ids = [int(pid.strip()) for pid in projects.split(",")]
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid project IDs: {projects}"
                }

        # Determine status filter for MCP
        status_filter = "all" if status == "all" else "open" if status == "open" else "closed"

        return self._call_tool_sync(
            "get_work_packages_by_date_range",
            start_date=start_date,
            end_date=end_date,
            project_ids=project_ids,
            status_filter=status_filter,
            group_by_project=True
        )

    def update_task(
        self,
        task_id: int,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
        assignee_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing work package.

        Args:
            task_id: Work package ID
            subject: New title
            description: New description
            status: New status
            due_date: New due date
            start_date: New start date
            assignee_email: New assignee email

        Returns:
            Result of the update
        """
        kwargs = {"work_package_id": task_id}

        if subject:
            kwargs["subject"] = subject
        if description:
            kwargs["description"] = description
        if status:
            kwargs["status"] = status
        if due_date:
            kwargs["due_date"] = due_date
        if start_date:
            kwargs["start_date"] = start_date

        result = self._call_tool_sync("update_work_package", **kwargs)

        # If assignee email provided, assign separately
        if assignee_email:
            self.assign_task_by_email(task_id, assignee_email)

        return result

    def delete_task(self, task_id: int) -> Dict[str, Any]:
        """Delete a work package.

        Args:
            task_id: Work package ID to delete

        Returns:
            Result of the deletion
        """
        # Note: OpenProject MCP may not have a delete tool.
        # This is a placeholder for the API contract.
        return {
            "success": False,
            "error": "Delete operation not yet implemented in MCP"
        }

    # ====== Dependency/Relation Commands ======

    def create_dependency(
        self,
        from_task_id: int,
        to_task_id: int,
        relation_type: str = "follows",
        description: str = ""
    ) -> Dict[str, Any]:
        """Create a link between work packages.

        Args:
            from_task_id: Source work package ID
            to_task_id: Target work package ID
            relation_type: Type of relation (follows, precedes, blocks, etc.)
            description: Notes about the relation

        Returns:
            Result with relation_id
        """
        return self._call_tool_sync(
            "create_work_package_dependency",
            from_work_package_id=from_task_id,
            to_work_package_id=to_task_id,
            relation_type=relation_type,
            description=description
        )

    # ====== Team/User Commands ======

    def get_project_team(self, project_id: int) -> Dict[str, Any]:
        """List all team members in a project.

        Args:
            project_id: Project ID

        Returns:
            List of project members with roles
        """
        return self._call_tool_sync(
            "get_project_members",
            project_id=project_id
        )

    def add_team_member(
        self,
        project_id: int,
        email: str,
        role: str = "Member"
    ) -> Dict[str, Any]:
        """Add a user to a project.

        Args:
            project_id: Project ID
            email: User email address
            role: Role in project

        Returns:
            Result of adding the member
        """
        return self._call_tool_sync(
            "assign_work_package_by_email",
            # This is a placeholder - actual implementation would depend on MCP
            project_id=project_id,
            email=email
        )

    def assign_task_by_email(self, task_id: int, assignee_email: str) -> Dict[str, Any]:
        """Assign a work package to a user by email.

        Args:
            task_id: Work package ID
            assignee_email: Email of assignee

        Returns:
            Result of the assignment
        """
        return self._call_tool_sync(
            "assign_work_package_by_email",
            work_package_id=task_id,
            assignee_email=assignee_email
        )


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="OpenProject CLI for NanoClaw integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list_projects
  %(prog)s create_task --project_id 5 --subject "My Task"
  %(prog)s get_tasks_by_date --date_range "today to +2" --status open
  %(prog)s update_task --task_id 234 --status "In Progress"
  %(prog)s create_dependency --from_task_id 234 --to_task_id 235
        """
    )

    parser.add_argument(
        "--mcp-url",
        default=os.getenv("OPENPROJECT_MCP_URL", "http://localhost:8085"),
        help="URL of OpenProject MCP server (default: http://localhost:8085)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Project Management Commands
    create_proj = subparsers.add_parser("create_project", help="Create a new project")
    create_proj.add_argument("--name", required=True, help="Project name")
    create_proj.add_argument("--description", default="", help="Project description")

    subparsers.add_parser("list_projects", help="List all projects")

    proj_summary = subparsers.add_parser("get_project_summary", help="Get project overview")
    proj_summary.add_argument("--project_id", type=int, required=True, help="Project ID")

    # Work Package Commands
    create_task = subparsers.add_parser("create_task", help="Create a new task")
    create_task.add_argument("--project_id", type=int, required=True, help="Project ID")
    create_task.add_argument("--subject", required=True, help="Task title")
    create_task.add_argument("--description", default="", help="Task description")
    create_task.add_argument("--start_date", help="Start date (YYYY-MM-DD)")
    create_task.add_argument("--due_date", help="Due date (YYYY-MM-DD)")
    create_task.add_argument("--assignee_email", help="Assignee email")
    create_task.add_argument("--estimated_hours", type=float, help="Estimated hours")

    get_tasks = subparsers.add_parser("get_tasks_by_date", help="Get tasks by date range")
    get_tasks.add_argument(
        "--date_range",
        required=True,
        help='Date range ("today", "today to +2", "YYYY-MM-DD to YYYY-MM-DD")'
    )
    get_tasks.add_argument("--projects", default="all", help="Project IDs (comma-separated) or 'all'")
    get_tasks.add_argument("--status", default="open", choices=["open", "closed", "all"], help="Status filter")

    update_task = subparsers.add_parser("update_task", help="Update a task")
    update_task.add_argument("--task_id", type=int, required=True, help="Work package ID")
    update_task.add_argument("--subject", help="New title")
    update_task.add_argument("--description", help="New description")
    update_task.add_argument("--status", help="New status")
    update_task.add_argument("--due_date", help="New due date")
    update_task.add_argument("--start_date", help="New start date")
    update_task.add_argument("--assignee_email", help="New assignee email")

    # Dependency Commands
    create_dep = subparsers.add_parser("create_dependency", help="Create task dependency")
    create_dep.add_argument("--from_task_id", type=int, required=True, help="Source task ID")
    create_dep.add_argument("--to_task_id", type=int, required=True, help="Target task ID")
    create_dep.add_argument("--relation_type", default="follows", help="Relation type")
    create_dep.add_argument("--description", default="", help="Relation description")

    # Team Commands
    team = subparsers.add_parser("get_project_team", help="List project team members")
    team.add_argument("--project_id", type=int, required=True, help="Project ID")

    args = parser.parse_args()

    # Initialize CLI
    cli = OpenProjectCLI(mcp_url=args.mcp_url)

    try:
        # Route to appropriate command
        if args.command == "create_project":
            result = cli.create_project(
                name=args.name,
                description=args.description
            )
        elif args.command == "list_projects":
            result = cli.list_projects()
        elif args.command == "get_project_summary":
            result = cli.get_project_summary(project_id=args.project_id)
        elif args.command == "create_task":
            result = cli.create_task(
                project_id=args.project_id,
                subject=args.subject,
                description=args.description,
                start_date=args.start_date,
                due_date=args.due_date,
                assignee_email=args.assignee_email,
                estimated_hours=args.estimated_hours
            )
        elif args.command == "get_tasks_by_date":
            result = cli.get_tasks_by_date(
                date_range=args.date_range,
                projects=args.projects,
                status=args.status
            )
        elif args.command == "update_task":
            result = cli.update_task(
                task_id=args.task_id,
                subject=args.subject,
                description=args.description,
                status=args.status,
                due_date=args.due_date,
                start_date=args.start_date,
                assignee_email=args.assignee_email
            )
        elif args.command == "create_dependency":
            result = cli.create_dependency(
                from_task_id=args.from_task_id,
                to_task_id=args.to_task_id,
                relation_type=args.relation_type,
                description=args.description
            )
        elif args.command == "get_project_team":
            result = cli.get_project_team(project_id=args.project_id)
        else:
            parser.print_help()
            return 1

        # Output result as JSON
        print(json.dumps(result, indent=2))
        return 0 if result.get("success", False) else 1

    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e)
        }
        print(json.dumps(error_result, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
