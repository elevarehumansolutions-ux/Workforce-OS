"use client";

// One dropdown for choosing a person, used everywhere a person is picked.
// People are grouped by the department of their position, and each is shown as "Name, Position":
//
//   Sales
//     Chidi Okafor, Sales Manager
//     Ada Eze, Sales Rep
//   Finance
//     Bola Ade, Accountant
//   No position yet
//     Tunde Bello

interface PersonLike {
  id: string;
  first_name: string;
  last_name: string;
  position_id?: string | null;
}

interface PositionLike {
  id: string;
  title: string;
  department_id: string;
}

interface DepartmentLike {
  id: string;
  name: string;
}

interface PersonSelectProps {
  people: PersonLike[];
  positions: PositionLike[];
  departments: DepartmentLike[];
  value: string;
  onChange: (personId: string) => void;
  // The first option, meaning "nobody chosen", for example "No one" or "Choose a person".
  emptyLabel: string;
  // An extra entry just under the first one, for a person who is currently chosen but no longer in
  // `people` (for example a department head who has since left): they still show instead of a blank.
  extraOption?: { id: string; label: string };
  disabled?: boolean;
  className?: string;
  id?: string;
}

interface Group {
  name: string;
  options: { id: string; label: string }[];
}

const NO_POSITION_GROUP = "No position yet";

function personName(person: PersonLike): string {
  return (person.first_name + " " + person.last_name).trim();
}

// Builds the groups: departments in alphabetical order, people alphabetical inside each,
// and the people without a position (or whose department is unknown) last.
function buildGroups(people: PersonLike[], positions: PositionLike[], departments: DepartmentLike[]): Group[] {
  const groupsByName: Record<string, Group> = {};

  for (const person of people) {
    const position = positions.find(function (p) { return p.id === person.position_id; });
    const department = position ? departments.find(function (d) { return d.id === position.department_id; }) : undefined;

    let groupName = NO_POSITION_GROUP;
    let label = personName(person);
    if (position && department) {
      groupName = department.name;
      label = personName(person) + ", " + position.title;
    } else if (position) {
      // A position whose department is missing from the list: still show the job.
      label = personName(person) + ", " + position.title;
    }

    if (!groupsByName[groupName]) {
      groupsByName[groupName] = { name: groupName, options: [] };
    }
    groupsByName[groupName].options.push({ id: person.id, label: label });
  }

  const groups = Object.values(groupsByName);
  for (const group of groups) {
    group.options.sort(function (a, b) { return a.label.localeCompare(b.label); });
  }
  groups.sort(function (a, b) {
    // "No position yet" always goes last.
    if (a.name === NO_POSITION_GROUP) return 1;
    if (b.name === NO_POSITION_GROUP) return -1;
    return a.name.localeCompare(b.name);
  });
  return groups;
}

export default function PersonSelect(props: PersonSelectProps) {
  const groups = buildGroups(props.people, props.positions, props.departments);
  const defaultClass =
    "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500 disabled:opacity-60";

  return (
    <select
      id={props.id}
      value={props.value}
      disabled={props.disabled}
      onChange={function (e) { props.onChange(e.target.value); }}
      className={props.className ? props.className : defaultClass}
    >
      <option value="">{props.emptyLabel}</option>
      {props.extraOption ? <option value={props.extraOption.id}>{props.extraOption.label}</option> : null}
      {groups.map(function (group) {
        return (
          <optgroup key={group.name} label={group.name}>
            {group.options.map(function (option) {
              return <option key={option.id} value={option.id}>{option.label}</option>;
            })}
          </optgroup>
        );
      })}
    </select>
  );
}
