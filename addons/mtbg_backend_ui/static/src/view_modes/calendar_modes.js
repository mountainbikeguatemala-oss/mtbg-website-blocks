/**
 * The calendars of Core's pages (Bookings, Departures, Bike Rentals...: a model on Core's boards) switch views like
 * their list and kanban: List · Cards · Kanban, then the calendar and the action's other views.
 */
import { patch } from "@web/core/utils/patch";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { useViewModes, ViewModes } from "./view_modes";

CalendarController.components = { ...CalendarController.components, ViewModes };

patch(CalendarController.prototype, {
    setup() {
        super.setup(...arguments);
        const types = (this.env.config.viewSwitcherEntries || []).map((e) => e.type);
        const ours = "mtbg_time_stage" in (this.props.fields || {}) && (types.includes("list") || types.includes("kanban"));
        this.mtbgViewEntries = ours ? useViewModes(this) : null;
    },
});
